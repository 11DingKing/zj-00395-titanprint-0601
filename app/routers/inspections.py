from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Order, QualityInspection, OrderStatus, OrderStatusHistory, InspectionResult,
    ProductionSchedule, PowderBatch, PowderBatchStatus, ReworkPriority,
)
from app.schemas import QualityInspectionCreate, QualityInspectionOut
from app.config import STATUS_LABELS

router = APIRouter(prefix="/inspections", tags=["quality-inspection"])


@router.post("/{order_id}", response_model=QualityInspectionOut, status_code=201)
def create_inspection(order_id: int, payload: QualityInspectionCreate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    if order.status != OrderStatus.inspecting and order.status != OrderStatus.printing:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，不能提交质检。"
            f"仅「打印中」或「质检中」状态的订单可提交质检",
        )

    if not payload.within_tolerance:
        if payload.repair_opinion is None or payload.repair_opinion.strip() == "":
            raise HTTPException(400, "超出容差的车架必须填写返修意见")

    inspection = QualityInspection(order_id=order_id, **payload.model_dump())
    db.add(inspection)
    db.flush()

    from_status = order.status
    need_rework = (not payload.within_tolerance) or (payload.flaw_detection_result == InspectionResult.fail)

    if payload.flaw_detection_result == InspectionResult.fail:
        latest_schedule = (
            db.query(ProductionSchedule)
            .filter(ProductionSchedule.order_id == order_id)
            .order_by(ProductionSchedule.created_at.desc())
            .first()
        )
        if latest_schedule:
            powder_batch = None
            if latest_schedule.powder_batch_id:
                powder_batch = (
                    db.query(PowderBatch)
                    .filter(PowderBatch.id == latest_schedule.powder_batch_id)
                    .first()
                )
            else:
                powder_batch = (
                    db.query(PowderBatch)
                    .filter(PowderBatch.batch_no == latest_schedule.powder_batch)
                    .first()
                )

            if powder_batch and powder_batch.status != PowderBatchStatus.quarantined:
                anomaly_note = f"订单 {order.order_no} 探伤检查不合格，怀疑粉末批次问题。探伤详情：{payload.flaw_detection_detail or '未提供'}"
                if powder_batch.anomaly_note:
                    powder_batch.anomaly_note = f"{powder_batch.anomaly_note}\n\n{anomaly_note}"
                else:
                    powder_batch.anomaly_note = anomaly_note
                powder_batch.status = PowderBatchStatus.warning

                all_schedules = (
                    db.query(ProductionSchedule)
                    .filter(
                        ProductionSchedule.powder_batch_id == powder_batch.id
                        if powder_batch.id else ProductionSchedule.powder_batch == powder_batch.batch_no
                    )
                    .all()
                )

                affected_order_ids = {s.order_id for s in all_schedules if s.order_id != order_id}

                for affected_oid in affected_order_ids:
                    affected_order = db.query(Order).filter(Order.id == affected_oid).first()
                    if affected_order and affected_order.status in [
                        OrderStatus.printing, OrderStatus.inspecting,
                        OrderStatus.assembly_ready, OrderStatus.rework
                    ]:
                        affected_inspection = (
                            db.query(QualityInspection)
                            .filter(QualityInspection.order_id == affected_oid)
                            .order_by(QualityInspection.inspected_at.desc())
                            .first()
                        )
                        if affected_inspection:
                            affected_inspection.needs_batch_review = True
                            if affected_inspection.rework_priority is None or \
                               affected_inspection.rework_priority in [ReworkPriority.low, ReworkPriority.medium]:
                                affected_inspection.rework_priority = ReworkPriority.high

                inspection.needs_batch_review = True
                inspection.rework_priority = ReworkPriority.urgent
                inspection.node_check_result = payload.node_check_result

    if need_rework:
        order.status = OrderStatus.rework
        reasons = []
        if not payload.within_tolerance:
            reasons.append("尺寸偏差超出容差")
        if payload.flaw_detection_result == InspectionResult.fail:
            reasons.append("探伤检查不通过")
        history_remark = f"质检结果不合格，转返修（{'、'.join(reasons)}）"
        if payload.repair_opinion:
            history_remark += f"；返修意见：{payload.repair_opinion}"
        if inspection.needs_batch_review:
            history_remark += "；已触发粉末批次异常关联复核"
    else:
        order.status = OrderStatus.assembly_ready
        history_remark = "质检通过（尺寸偏差在容差范围内，探伤检查合格），车架可装配"

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=order.status,
        operator=payload.inspector,
        remark=history_remark,
    )
    db.add(history)

    db.commit()
    db.refresh(inspection)
    return inspection


@router.get("/order/{order_id}", response_model=list[QualityInspectionOut])
def get_order_inspections(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    return (
        db.query(QualityInspection)
        .filter(QualityInspection.order_id == order_id)
        .order_by(QualityInspection.inspected_at.desc())
        .all()
    )


@router.get("/{inspection_id}", response_model=QualityInspectionOut)
def get_inspection(inspection_id: int, db: Session = Depends(get_db)):
    inspection = db.query(QualityInspection).filter(QualityInspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(404, "质检记录不存在")
    return inspection
