from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models import (
    Order, ProductionSchedule, PrintEquipment, OrderStatus, OrderStatusHistory,
    PowderBatch, PowderBatchStatus,
)
from app.schemas import (
    ProductionScheduleCreate, ProductionScheduleOut, ScheduleConflictOut,
    PowderBatchOut,
)
from app.config import VALID_TRANSITIONS, STATUS_LABELS

router = APIRouter(prefix="/schedules", tags=["production-scheduling"])


def _check_conflicts(
    db: Session, equipment_id: int, start: datetime, end: datetime, exclude_id: int | None = None
) -> list[ScheduleConflictOut]:
    q = db.query(ProductionSchedule).filter(
        ProductionSchedule.equipment_id == equipment_id,
        ProductionSchedule.print_start < end,
        ProductionSchedule.print_end > start,
    )
    if exclude_id:
        q = q.filter(ProductionSchedule.id != exclude_id)

    conflicts = []
    for s in q.all():
        conflicts.append(
            ScheduleConflictOut(
                conflicting_schedule_id=s.id,
                conflicting_order_no=s.order.order_no,
                print_start=s.print_start,
                print_end=s.print_end,
            )
        )
    return conflicts


@router.post("/{order_id}", response_model=ProductionScheduleOut, status_code=201)
def create_schedule(order_id: int, payload: ProductionScheduleCreate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    if not order.confirmation:
        raise HTTPException(400, "订单尚未经工程师确认，无法排产")

    if order.status != OrderStatus.pending and order.status != OrderStatus.rework:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，不能排产。"
            f"仅「待确认」或「返修」状态的订单可排产",
        )

    equipment = db.query(PrintEquipment).filter(PrintEquipment.id == payload.equipment_id).first()
    if not equipment:
        raise HTTPException(404, "打印设备不存在")
    if not equipment.active:
        raise HTTPException(400, "该打印设备已停用")

    if payload.print_end <= payload.print_start:
        raise HTTPException(400, "打印结束时间必须晚于开始时间")

    if payload.heat_treat_start and payload.heat_treat_end:
        if payload.heat_treat_end <= payload.heat_treat_start:
            raise HTTPException(400, "热处理结束时间必须晚于开始时间")

    powder_batch_ref = None
    warnings = []
    if payload.powder_batch_id:
        powder_batch_ref = db.query(PowderBatch).filter(PowderBatch.id == payload.powder_batch_id).first()
        if not powder_batch_ref:
            raise HTTPException(400, f"指定的粉末批次 ID {payload.powder_batch_id} 不存在")

        if powder_batch_ref.status == PowderBatchStatus.quarantined:
            raise HTTPException(
                400,
                f"粉末批次「{powder_batch_ref.batch_no}」已被隔离，禁止用于排产。"
                f"异常说明：{powder_batch_ref.anomaly_note}",
            )
        if powder_batch_ref.status == PowderBatchStatus.warning:
            warnings.append(f"粉末批次「{powder_batch_ref.batch_no}」存在异常警告：{powder_batch_ref.anomaly_note}")
        if powder_batch_ref.status == PowderBatchStatus.depleted:
            warnings.append(f"粉末批次「{powder_batch_ref.batch_no}」已耗尽，建议更换批次")
        if powder_batch_ref.recycling_count >= powder_batch_ref.max_recycling:
            warnings.append(f"粉末批次「{powder_batch_ref.batch_no}」已达最大回收次数 {powder_batch_ref.max_recycling}")
        if powder_batch_ref.remaining_weight_kg <= 0:
            warnings.append(f"粉末批次「{powder_batch_ref.batch_no}」剩余重量不足")
    else:
        powder_batch_ref = db.query(PowderBatch).filter(PowderBatch.batch_no == payload.powder_batch).first()
        if powder_batch_ref:
            if powder_batch_ref.status == PowderBatchStatus.quarantined:
                raise HTTPException(
                    400,
                    f"粉末批次「{powder_batch_ref.batch_no}」已被隔离，禁止用于排产。"
                    f"异常说明：{powder_batch_ref.anomaly_note}",
                )
            if powder_batch_ref.status == PowderBatchStatus.warning:
                warnings.append(f"粉末批次「{powder_batch_ref.batch_no}」存在异常警告：{powder_batch_ref.anomaly_note}")

    conflicts = _check_conflicts(db, payload.equipment_id, payload.print_start, payload.print_end)
    if conflicts:
        raise HTTPException(
            409,
            {
                "detail": "设备时段冲突",
                "conflicts": [c.model_dump(mode="json") for c in conflicts],
            },
        )

    duration_hours = (payload.print_end - payload.print_start).total_seconds() / 3600

    schedule = ProductionSchedule(
        order_id=order_id,
        equipment_id=payload.equipment_id,
        powder_batch_id=powder_batch_ref.id if powder_batch_ref else None,
        powder_batch=payload.powder_batch,
        recycling_count=payload.recycling_count,
        heat_treat_window_low_c=payload.heat_treat_window_low_c,
        heat_treat_window_high_c=payload.heat_treat_window_high_c,
        print_start=payload.print_start,
        print_end=payload.print_end,
        heat_treat_start=payload.heat_treat_start,
        heat_treat_end=payload.heat_treat_end,
        print_duration_hours=payload.print_duration_hours or duration_hours,
    )
    db.add(schedule)

    from_status = order.status
    order.status = OrderStatus.scheduled
    remark = f"打印排产已创建，设备：{equipment.name}"
    if warnings:
        remark += f"。注意：{'；'.join(warnings)}"
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.scheduled,
        operator=None,
        remark=remark,
    )
    db.add(history)

    db.commit()
    db.refresh(schedule)

    result = ProductionScheduleOut.model_validate(schedule)
    if powder_batch_ref:
        result.powder_batch_info = PowderBatchOut.model_validate(powder_batch_ref)
    return result


@router.get("/check-conflicts", response_model=list[ScheduleConflictOut])
def check_conflicts(
    equipment_id: int,
    print_start: datetime,
    print_end: datetime,
    db: Session = Depends(get_db),
):
    return _check_conflicts(db, equipment_id, print_start, print_end)


@router.get("/order/{order_id}", response_model=list[ProductionScheduleOut])
def get_order_schedules(order_id: int, db: Session = Depends(get_db)):
    schedules = db.query(ProductionSchedule).filter(ProductionSchedule.order_id == order_id).all()
    result = []
    for sched in schedules:
        out = ProductionScheduleOut.model_validate(sched)
        if sched.powder_batch_ref:
            out.powder_batch_info = PowderBatchOut.model_validate(sched.powder_batch_ref)
        result.append(out)
    return result


@router.get("/equipment/{equipment_id}", response_model=list[ProductionScheduleOut])
def get_equipment_schedules(
    equipment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return (
        db.query(ProductionSchedule)
        .filter(ProductionSchedule.equipment_id == equipment_id)
        .order_by(ProductionSchedule.print_start)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(ProductionSchedule).filter(ProductionSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "排产记录不存在")

    order_id = schedule.order_id
    db.delete(schedule)
    db.flush()

    remaining = (
        db.query(ProductionSchedule)
        .filter(ProductionSchedule.order_id == order_id)
        .count()
    )
    if remaining == 0:
        order = db.query(Order).filter(Order.id == order_id).first()
        if order and order.status == OrderStatus.scheduled:
            from_status = order.status
            order.status = OrderStatus.pending
            history = OrderStatusHistory(
                order_id=order.id,
                from_status=from_status,
                to_status=OrderStatus.pending,
                operator=None,
                remark="最后一条排产记录已删除，订单回退至待确认状态",
            )
            db.add(history)

    db.commit()


@router.post("/{schedule_id}/start-print", response_model=ProductionScheduleOut)
def start_printing(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(ProductionSchedule).filter(ProductionSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "排产记录不存在")

    order = db.query(Order).filter(Order.id == schedule.order_id).first()
    if order.status != OrderStatus.scheduled:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，"
            f"仅「已排产」状态的订单可开始打印",
        )

    from_status = order.status
    order.status = OrderStatus.printing
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.printing,
        operator=None,
        remark=f"开始打印，设备：{schedule.equipment.name}",
    )
    db.add(history)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.post("/{schedule_id}/finish-print", response_model=ProductionScheduleOut)
def finish_printing(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(ProductionSchedule).filter(ProductionSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "排产记录不存在")

    order = db.query(Order).filter(Order.id == schedule.order_id).first()
    if order.status != OrderStatus.printing:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，"
            f"仅「打印中」状态的订单可完成打印",
        )

    from_status = order.status
    order.status = OrderStatus.inspecting
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.inspecting,
        operator=None,
        remark=f"打印完成，转入质检",
    )
    db.add(history)
    db.commit()
    db.refresh(schedule)
    return schedule
