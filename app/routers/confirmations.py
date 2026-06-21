from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Order, EngineerConfirmation, OrderStatus, OrderStatusHistory,
    GeometryChangeRequest, ChangeReviewStatus,
)
from app.schemas import (
    EngineerConfirmationCreate, EngineerConfirmationOut,
    EngineerConfirmationUpdate, EngineerConfirmationHistoryOut,
)
from app.config import STATUS_LABELS

router = APIRouter(prefix="/orders/{order_id}/confirmation", tags=["engineer-confirmation"])


def _get_active_version(db: Session, order_id: int) -> int:
    max_ver = (
        db.query(EngineerConfirmation)
        .filter(EngineerConfirmation.order_id == order_id)
        .count()
    )
    return max_ver + 1


def _get_pending_change_request(
    db: Session, order_id: int
) -> GeometryChangeRequest | None:
    return (
        db.query(GeometryChangeRequest)
        .filter(
            GeometryChangeRequest.order_id == order_id,
            GeometryChangeRequest.status == ChangeReviewStatus.approved,
        )
        .order_by(GeometryChangeRequest.created_at.desc())
        .first()
    )


@router.post("/", response_model=EngineerConfirmationOut, status_code=201)
def create_confirmation(
    order_id: int, payload: EngineerConfirmationCreate, db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.confirmation:
        raise HTTPException(
            400,
            "该订单已有工程师确认记录，如需修改请调用重新确认接口（PUT）",
        )

    if order.status not in [OrderStatus.pending, OrderStatus.change_pending]:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，"
            f"仅「待确认」或「变更待确认」状态可执行首次工程师确认",
        )

    version = _get_active_version(db, order_id)
    pending_change = _get_pending_change_request(db, order_id)
    confirmation = EngineerConfirmation(
        order_id=order_id,
        version=version,
        is_active=True,
        change_request_id=pending_change.id if pending_change else None,
        **payload.model_dump(),
    )
    db.add(confirmation)

    from_status = order.status
    if order.status == OrderStatus.change_pending:
        order.status = OrderStatus.pending
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=OrderStatus.pending,
            operator=payload.engineer_name,
            remark=(
                f"工程师「{payload.engineer_name}」完成参数变更后的重新确认，"
                f"车架尺寸、管壁厚度（{payload.wall_thickness_mm}mm）、"
                f"节点类型（{payload.node_type}）、目标重量（{payload.target_weight_g}g）已更新，"
                f"订单转入待排产状态。"
            ),
        )
    else:
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=from_status,
            operator=payload.engineer_name,
            remark=f"工程师「{payload.engineer_name}」完成首次车架参数确认",
        )
    db.add(history)

    db.commit()
    db.refresh(confirmation)
    return confirmation


@router.put("/reconfirm", response_model=EngineerConfirmationOut)
def reconfirm_after_change(
    order_id: int, payload: EngineerConfirmationUpdate, db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    if order.status != OrderStatus.change_pending:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，"
            f"仅「变更待确认」状态的订单可执行重新确认。"
            f"若为首次确认，请使用 POST 接口。",
        )

    for c in order.confirmation_list:
        c.is_active = False

    version = _get_active_version(db, order_id)
    pending_change = _get_pending_change_request(db, order_id)

    new_confirmation = EngineerConfirmation(
        order_id=order_id,
        version=version,
        is_active=True,
        change_request_id=pending_change.id if pending_change else None,
        frame_size_label=payload.frame_size_label,
        stack_mm=payload.stack_mm,
        reach_mm=payload.reach_mm,
        head_angle_deg=payload.head_angle_deg,
        seat_angle_deg=payload.seat_angle_deg,
        chainstay_mm=payload.chainstay_mm,
        wheelbase_mm=payload.wheelbase_mm,
        wall_thickness_mm=payload.wall_thickness_mm,
        node_type=payload.node_type,
        node_strength_rating=payload.node_strength_rating,
        target_weight_g=payload.target_weight_g,
        engineer_name=payload.engineer_name,
        remarks=payload.remarks,
    )
    db.add(new_confirmation)

    from_status = order.status
    order.status = OrderStatus.pending

    strength_msg = (
        f"节点强度等级 {payload.node_strength_rating}"
        if payload.node_strength_rating else "节点强度复核通过"
    )
    history_remark = (
        f"几何参数变更后工程师「{payload.engineer_name}」重新确认 (v{version})："
        f"车架尺寸 {payload.frame_size_label}、"
        f"管壁厚度 {payload.wall_thickness_mm}mm、"
        f"{strength_msg}、"
        f"目标重量 {payload.target_weight_g}g。"
        f"变更后质检基准已同步更新，可重新排产。"
    )
    if payload.remarks:
        history_remark += f" 备注：{payload.remarks}"
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=OrderStatus.pending,
        operator=payload.engineer_name,
        remark=history_remark,
    )
    db.add(history)

    db.commit()
    db.refresh(new_confirmation)
    return EngineerConfirmationOut.model_validate(new_confirmation)


@router.get("/", response_model=EngineerConfirmationOut)
def get_confirmation(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    if not order.confirmation:
        raise HTTPException(404, "该订单尚无工程师确认记录")
    return order.confirmation


@router.get("/history", response_model=list[EngineerConfirmationHistoryOut])
def get_confirmation_history(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    return (
        db.query(EngineerConfirmation)
        .filter(EngineerConfirmation.order_id == order_id)
        .order_by(EngineerConfirmation.version.asc())
        .all()
    )
