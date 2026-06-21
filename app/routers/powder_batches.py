from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    PowderBatch, PowderBatchStatus, ProductionSchedule, Order,
    QualityInspection, InspectionResult, ReworkPriority,
)
from app.schemas import (
    PowderBatchCreate, PowderBatchUpdate, PowderBatchOut,
    AffectedOrderOut, BatchAnomalyReport, BatchReviewUpdate,
    QualityInspectionOut,
)

router = APIRouter(prefix="/powder-batches", tags=["powder-batch-tracking"])


@router.post("/", response_model=PowderBatchOut, status_code=201)
def create_powder_batch(payload: PowderBatchCreate, db: Session = Depends(get_db)):
    existing = db.query(PowderBatch).filter(PowderBatch.batch_no == payload.batch_no).first()
    if existing:
        raise HTTPException(400, f"粉末批次号 {payload.batch_no} 已存在")

    if payload.remaining_weight_kg > payload.initial_weight_kg:
        raise HTTPException(400, "剩余重量不能大于初始重量")

    if payload.recycling_count > payload.max_recycling:
        raise HTTPException(400, "回收次数不能大于最大允许回收次数")

    batch = PowderBatch(**payload.model_dump())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/", response_model=list[PowderBatchOut])
def list_powder_batches(
    status: PowderBatchStatus | None = None,
    material: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(PowderBatch)
    if status:
        q = q.filter(PowderBatch.status == status)
    if material:
        q = q.filter(PowderBatch.material.like(f"%{material}%"))
    return q.order_by(PowderBatch.id.desc()).offset(skip).limit(limit).all()


@router.get("/{batch_id}", response_model=PowderBatchOut)
def get_powder_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(PowderBatch).filter(PowderBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")
    return batch


@router.get("/by-no/{batch_no}", response_model=PowderBatchOut)
def get_powder_batch_by_no(batch_no: str, db: Session = Depends(get_db)):
    batch = db.query(PowderBatch).filter(PowderBatch.batch_no == batch_no).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")
    return batch


@router.put("/{batch_id}", response_model=PowderBatchOut)
def update_powder_batch(
    batch_id: int, payload: PowderBatchUpdate, db: Session = Depends(get_db)
):
    batch = db.query(PowderBatch).filter(PowderBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")

    update_data = payload.model_dump(exclude_unset=True)

    if "remaining_weight_kg" in update_data:
        initial = update_data.get("initial_weight_kg", batch.initial_weight_kg)
        if update_data["remaining_weight_kg"] > initial:
            raise HTTPException(400, "剩余重量不能大于初始重量")

    if "recycling_count" in update_data:
        max_rec = update_data.get("max_recycling", batch.max_recycling)
        if update_data["recycling_count"] > max_rec:
            raise HTTPException(400, "回收次数不能大于最大允许回收次数")

    for key, value in update_data.items():
        setattr(batch, key, value)

    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/mark-anomaly", response_model=BatchAnomalyReport)
def mark_batch_anomaly(
    batch_id: int,
    anomaly_note: str = Query(..., description="异常说明"),
    auto_quarantine: bool = Query(True, description="是否自动标记为隔离"),
    auto_flag_orders: bool = Query(True, description="是否自动标记关联订单需复核"),
    db: Session = Depends(get_db),
):
    batch = db.query(PowderBatch).filter(PowderBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")

    if auto_quarantine:
        batch.status = PowderBatchStatus.quarantined
    batch.anomaly_note = anomaly_note

    affected_orders = _get_affected_orders(db, batch.id, batch.batch_no)

    if auto_flag_orders:
        for ao in affected_orders:
            inspection = (
                db.query(QualityInspection)
                .filter(QualityInspection.order_id == ao["order_id"])
                .order_by(QualityInspection.inspected_at.desc())
                .first()
            )
            if inspection:
                inspection.needs_batch_review = True
                inspection.rework_priority = ReworkPriority.urgent

    db.commit()

    affected_out = [AffectedOrderOut(**ao) for ao in affected_orders]

    return BatchAnomalyReport(
        batch_id=batch.id,
        batch_no=batch.batch_no,
        affected_orders_count=len(affected_out),
        affected_orders=affected_out,
        anomaly_note=anomaly_note,
    )


@router.get("/{batch_id}/affected-orders", response_model=list[AffectedOrderOut])
def get_affected_orders(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(PowderBatch).filter(PowderBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")

    affected = _get_affected_orders(db, batch.id, batch.batch_no)
    return [AffectedOrderOut(**ao) for ao in affected]


@router.get("/by-no/{batch_no}/affected-orders", response_model=list[AffectedOrderOut])
def get_affected_orders_by_no(batch_no: str, db: Session = Depends(get_db)):
    batch = db.query(PowderBatch).filter(PowderBatch.batch_no == batch_no).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")

    affected = _get_affected_orders(db, batch.id, batch.batch_no)
    return [AffectedOrderOut(**ao) for ao in affected]


@router.post("/{batch_id}/resolve-anomaly", response_model=PowderBatchOut)
def resolve_batch_anomaly(
    batch_id: int,
    resolution_note: str = Query(..., description="处理说明"),
    new_status: PowderBatchStatus = Query(PowderBatchStatus.normal, description="新状态"),
    db: Session = Depends(get_db),
):
    batch = db.query(PowderBatch).filter(PowderBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "粉末批次不存在")

    batch.status = new_status
    batch.anomaly_note = f"{batch.anomaly_note or ''}\n\n处理结果：{resolution_note}" if batch.anomaly_note else resolution_note

    db.commit()
    db.refresh(batch)
    return batch


@router.get("/orders/{order_id}/batch-review", response_model=list[QualityInspectionOut])
def get_order_batch_reviews(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    return (
        db.query(QualityInspection)
        .filter(
            QualityInspection.order_id == order_id,
            QualityInspection.needs_batch_review.is_(True),
        )
        .order_by(QualityInspection.inspected_at.desc())
        .all()
    )


@router.put("/inspections/{inspection_id}/batch-review", response_model=QualityInspectionOut)
def update_batch_review(
    inspection_id: int, payload: BatchReviewUpdate, db: Session = Depends(get_db)
):
    inspection = db.query(QualityInspection).filter(QualityInspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(404, "质检记录不存在")

    if not inspection.needs_batch_review:
        raise HTTPException(400, "该质检记录无需批次复核")

    inspection.batch_review_completed = payload.batch_review_completed
    inspection.batch_review_note = payload.batch_review_note
    inspection.batch_reviewed_by = payload.batch_reviewed_by
    inspection.batch_reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(inspection)
    return inspection


def _get_affected_orders(db: Session, batch_id: int, batch_no: str) -> list[dict]:
    schedules = (
        db.query(ProductionSchedule)
        .filter(
            and_(
                ProductionSchedule.powder_batch_id == batch_id,
            )
        )
        .all()
    )

    if not schedules:
        schedules = (
            db.query(ProductionSchedule)
            .filter(ProductionSchedule.powder_batch == batch_no)
            .all()
        )

    affected = []
    for sched in schedules:
        order = sched.order
        latest_inspection = (
            db.query(QualityInspection)
            .filter(QualityInspection.order_id == order.id)
            .order_by(QualityInspection.inspected_at.desc())
            .first()
        )

        affected.append({
            "order_id": order.id,
            "order_no": order.order_no,
            "customer_name": order.customer_name,
            "status": order.status,
            "schedule_id": sched.id,
            "print_start": sched.print_start,
            "inspection_result": latest_inspection.flaw_detection_result if latest_inspection else None,
            "rework_priority": latest_inspection.rework_priority if latest_inspection else None,
            "needs_batch_review": latest_inspection.needs_batch_review if latest_inspection else None,
        })

    return affected
