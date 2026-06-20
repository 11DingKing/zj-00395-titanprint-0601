from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    PrintEquipment, ProductionSchedule, QualityInspection, Order, OrderStatus,
    OrderStatusHistory,
)
from app.schemas import EquipmentUtilizationOut, ReworkRateOut, DeliveryCycleOut

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/equipment-utilization", response_model=list[EquipmentUtilizationOut])
def equipment_utilization(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    equipments = db.query(PrintEquipment).filter(PrintEquipment.active.is_(True)).all()

    if not start:
        earliest = db.query(func.min(ProductionSchedule.print_start)).scalar()
        start = earliest or datetime.utcnow()
    if not end:
        end = datetime.utcnow()

    total_hours = (end - start).total_seconds() / 3600
    if total_hours <= 0:
        return []

    result = []
    for eq in equipments:
        sched_hours = (
            db.query(func.coalesce(func.sum(ProductionSchedule.print_duration_hours), 0))
            .filter(
                ProductionSchedule.equipment_id == eq.id,
                ProductionSchedule.print_start >= start,
                ProductionSchedule.print_end <= end,
            )
            .scalar()
        )
        result.append(
            EquipmentUtilizationOut(
                equipment_id=eq.id,
                equipment_name=eq.name,
                total_scheduled_hours=round(sched_hours, 2),
                utilization_rate=round(sched_hours / total_hours, 4) if total_hours > 0 else 0,
            )
        )
    return result


@router.get("/rework-rate", response_model=list[ReworkRateOut])
def rework_rate(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    equipments = db.query(PrintEquipment).all()
    result = []

    for eq in equipments:
        schedule_ids = (
            db.query(ProductionSchedule.id)
            .filter(ProductionSchedule.equipment_id == eq.id)
        )
        if start:
            schedule_ids = schedule_ids.filter(ProductionSchedule.print_start >= start)
        if end:
            schedule_ids = schedule_ids.filter(ProductionSchedule.print_end <= end)
        schedule_ids = schedule_ids.subquery()

        order_ids = (
            db.query(ProductionSchedule.order_id)
            .filter(ProductionSchedule.id.in_(schedule_ids))
            .distinct()
            .subquery()
        )

        total = db.query(func.count(Order.id)).filter(Order.id.in_(order_ids)).scalar() or 0
        rework_count = (
            db.query(func.count(OrderStatusHistory.id))
            .filter(
                OrderStatusHistory.order_id.in_(order_ids),
                OrderStatusHistory.to_status == OrderStatus.rework,
            )
            .scalar()
            or 0
        )

        result.append(
            ReworkRateOut(
                equipment_id=eq.id,
                equipment_name=eq.name,
                total_orders=total,
                rework_orders=rework_count,
                rework_rate=round(rework_count / total, 4) if total > 0 else 0,
            )
        )
    return result


@router.get("/delivery-cycle", response_model=list[DeliveryCycleOut])
def delivery_cycle(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    equipments = db.query(PrintEquipment).all()
    result = []

    for eq in equipments:
        schedule_q = db.query(ProductionSchedule).filter(ProductionSchedule.equipment_id == eq.id)
        if start:
            schedule_q = schedule_q.filter(ProductionSchedule.print_start >= start)
        if end:
            schedule_q = schedule_q.filter(ProductionSchedule.print_end <= end)
        schedules = schedule_q.all()

        order_ids = list({s.order_id for s in schedules})

        delivery_hours_list = []
        for oid in order_ids:
            created = (
                db.query(func.min(OrderStatusHistory.created_at))
                .filter(
                    OrderStatusHistory.order_id == oid,
                    OrderStatusHistory.to_status == OrderStatus.pending,
                )
                .scalar()
            )
            delivered = (
                db.query(func.min(OrderStatusHistory.created_at))
                .filter(
                    OrderStatusHistory.order_id == oid,
                    OrderStatusHistory.to_status == OrderStatus.assembly_ready,
                )
                .scalar()
            )
            if created and delivered:
                delivery_hours_list.append((delivered - created).total_seconds() / 3600)

        avg_hours = None
        if delivery_hours_list:
            avg_hours = round(sum(delivery_hours_list) / len(delivery_hours_list), 2)

        result.append(
            DeliveryCycleOut(
                equipment_id=eq.id,
                equipment_name=eq.name,
                average_delivery_hours=avg_hours,
                order_count=len(delivery_hours_list),
            )
        )
    return result
