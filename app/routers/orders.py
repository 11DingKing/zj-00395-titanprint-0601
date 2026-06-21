from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Order, CustomerSpec, OrderStatusHistory, OrderStatus, QualityInspection,
    InspectionResult, ProductionSchedule, ReworkPriority,
)
from app.schemas import (
    OrderCreate, OrderOut, OrderListOut, StatusTransition, StatusHistoryOut,
)
from app.config import VALID_TRANSITIONS, STATUS_LABELS

router = APIRouter(prefix="/orders", tags=["orders"])


def _generate_order_no(db: Session) -> str:
    from datetime import datetime
    prefix = datetime.utcnow().strftime("TP%Y%m%d")
    last = (
        db.query(Order)
        .filter(Order.order_no.like(f"{prefix}%"))
        .order_by(Order.id.desc())
        .first()
    )
    seq = 1
    if last and last.order_no.startswith(prefix):
        seq = int(last.order_no[len(prefix):]) + 1
    return f"{prefix}{seq:04d}"


@router.post("/", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    order_no = _generate_order_no(db)
    order = Order(
        order_no=order_no,
        customer_name=payload.customer_name,
        customer_contact=payload.customer_contact,
    )
    db.add(order)
    db.flush()

    spec = CustomerSpec(order_id=order.id, **payload.spec.model_dump())
    db.add(spec)

    history = OrderStatusHistory(
        order_id=order.id,
        from_status=None,
        to_status=OrderStatus.pending,
        operator=None,
        remark="订单创建",
    )
    db.add(history)
    db.commit()
    db.refresh(order)
    return order


def _enrich_order_out(db: Session, order, out_model):
    latest_schedule = (
        db.query(ProductionSchedule)
        .filter(ProductionSchedule.order_id == order.id)
        .order_by(ProductionSchedule.created_at.desc())
        .first()
    )
    latest_inspection = (
        db.query(QualityInspection)
        .filter(QualityInspection.order_id == order.id)
        .order_by(QualityInspection.inspected_at.desc())
        .first()
    )

    out = out_model.model_validate(order)
    if latest_schedule:
        out.powder_batch = latest_schedule.powder_batch
    if latest_inspection:
        out.rework_priority = latest_inspection.rework_priority
        out.needs_batch_review = latest_inspection.needs_batch_review
    return out


@router.get("/", response_model=list[OrderListOut])
def list_orders(
    status: OrderStatus | None = None,
    powder_batch: str | None = None,
    powder_batch_id: int | None = None,
    needs_batch_review: bool | None = None,
    rework_priority: ReworkPriority | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Order)
    if status:
        q = q.filter(Order.status == status)

    if powder_batch_id:
        schedule_ids = select(ProductionSchedule.order_id).filter(
            ProductionSchedule.powder_batch_id == powder_batch_id
        )
        q = q.filter(Order.id.in_(schedule_ids))
    elif powder_batch:
        schedule_ids = select(ProductionSchedule.order_id).filter(
            ProductionSchedule.powder_batch == powder_batch
        )
        q = q.filter(Order.id.in_(schedule_ids))

    if needs_batch_review is not None or rework_priority:
        inspection_subq = select(QualityInspection.order_id).distinct()
        if needs_batch_review is not None:
            inspection_subq = inspection_subq.filter(
                QualityInspection.needs_batch_review == needs_batch_review
            )
        if rework_priority:
            inspection_subq = inspection_subq.filter(
                QualityInspection.rework_priority == rework_priority
            )
        q = q.filter(Order.id.in_(inspection_subq))

    orders = q.order_by(Order.id.desc()).offset(skip).limit(limit).all()
    return [_enrich_order_out(db, o, OrderListOut) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    return _enrich_order_out(db, order, OrderOut)


@router.post("/{order_id}/transition", response_model=OrderOut)
def transition_status(order_id: int, payload: StatusTransition, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    current = order.status.value
    target = payload.to_status.value
    allowed = VALID_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise HTTPException(
            400,
            f"状态流转不合法：{STATUS_LABELS.get(current, current)} → {STATUS_LABELS.get(target, target)}，"
            f"允许的目标状态：{[STATUS_LABELS.get(s, s) for s in allowed]}",
        )

    if payload.to_status == OrderStatus.assembly_ready:
        latest_inspection = (
            db.query(QualityInspection)
            .filter(QualityInspection.order_id == order_id)
            .order_by(QualityInspection.inspected_at.desc())
            .first()
        )
        if not latest_inspection:
            raise HTTPException(400, "该订单尚无质检记录，不能标记为可装配")
        blockers = []
        if not latest_inspection.within_tolerance:
            blockers.append("尺寸偏差超出容差")
        if latest_inspection.flaw_detection_result == InspectionResult.fail:
            blockers.append("探伤检查不通过")
        if blockers:
            raise HTTPException(
                400,
                f"车架不可装配：{'、'.join(blockers)}。请先完成返修并重新质检合格。",
            )

    order.status = payload.to_status
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=OrderStatus(current),
        to_status=payload.to_status,
        operator=payload.operator,
        remark=payload.remark,
    )
    db.add(history)
    db.commit()
    db.refresh(order)
    return _enrich_order_out(db, order, OrderOut)


@router.get("/{order_id}/history", response_model=list[StatusHistoryOut])
def get_status_history(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    return (
        db.query(OrderStatusHistory)
        .filter(OrderStatusHistory.order_id == order_id)
        .order_by(OrderStatusHistory.created_at)
        .all()
    )
