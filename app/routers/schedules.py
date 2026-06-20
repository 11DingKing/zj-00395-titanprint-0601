from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models import Order, ProductionSchedule, PrintEquipment, OrderStatus
from app.schemas import (
    ProductionScheduleCreate, ProductionScheduleOut, ScheduleConflictOut,
)

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
        powder_batch=payload.powder_batch,
        print_start=payload.print_start,
        print_end=payload.print_end,
        heat_treat_start=payload.heat_treat_start,
        heat_treat_end=payload.heat_treat_end,
        print_duration_hours=payload.print_duration_hours or duration_hours,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


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
    return db.query(ProductionSchedule).filter(ProductionSchedule.order_id == order_id).all()


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
    db.delete(schedule)
    db.commit()
