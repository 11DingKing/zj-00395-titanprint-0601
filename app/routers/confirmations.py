from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, EngineerConfirmation, OrderStatus
from app.schemas import EngineerConfirmationCreate, EngineerConfirmationOut

router = APIRouter(prefix="/orders/{order_id}/confirmation", tags=["engineer-confirmation"])


@router.post("/", response_model=EngineerConfirmationOut, status_code=201)
def create_confirmation(order_id: int, payload: EngineerConfirmationCreate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.confirmation:
        raise HTTPException(400, "该订单已有工程师确认记录")

    confirmation = EngineerConfirmation(order_id=order_id, **payload.model_dump())
    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)
    return confirmation


@router.get("/", response_model=EngineerConfirmationOut)
def get_confirmation(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    if not order.confirmation:
        raise HTTPException(404, "该订单尚无工程师确认记录")
    return order.confirmation
