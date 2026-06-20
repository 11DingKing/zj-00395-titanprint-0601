from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, QualityInspection, OrderStatus
from app.schemas import QualityInspectionCreate, QualityInspectionOut

router = APIRouter(prefix="/inspections", tags=["quality-inspection"])


@router.post("/{order_id}", response_model=QualityInspectionOut, status_code=201)
def create_inspection(order_id: int, payload: QualityInspectionCreate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    if not payload.within_tolerance:
        if payload.repair_opinion is None or payload.repair_opinion.strip() == "":
            raise HTTPException(400, "超出容差的车架必须填写返修意见")

    inspection = QualityInspection(order_id=order_id, **payload.model_dump())
    db.add(inspection)
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
