from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Order, CustomerSpec, OrderStatus, OrderStatusHistory,
    ProductionSchedule, GeometryChangeRequest, ChangeReviewStatus,
    EngineerConfirmation, PrintEquipment,
)
from app.schemas import (
    GeometryChangeRequestCreate, GeometryChangeRequestOut,
    GeometryChangeSpecSnapshot, ChangeReview, OrderChangeSummaryOut,
)
from app.config import (
    VALID_TRANSITIONS, STATUS_LABELS, CHANGE_TYPE_LABELS,
    CHANGE_REVIEW_STATUS_LABELS, DEFAULT_RECONFIRM_DELAY_HOURS,
    PRINTING_CHANGE_REVIEW_REQUIRED,
)

router = APIRouter(prefix="/geometry-changes", tags=["geometry-changes"])


def _detect_change_types(payload: GeometryChangeRequestCreate) -> list[str]:
    types = []
    if payload.new_height_cm is not None:
        types.append("height")
    if payload.new_inseam_cm is not None:
        types.append("inseam")
    if payload.new_riding_posture is not None:
        types.append("riding_posture")
    if payload.new_usage is not None:
        types.append("usage")
    if not types and (
        payload.new_desired_stack is not None
        or payload.new_desired_reach is not None
        or payload.new_desired_head_angle is not None
        or payload.new_desired_seat_angle is not None
        or payload.new_desired_wheelbase is not None
        or payload.new_notes is not None
    ):
        types.append("other")
    return types


def _build_change_request_out(
    req: GeometryChangeRequest,
) -> GeometryChangeRequestOut:
    old_spec = GeometryChangeSpecSnapshot(
        height_cm=req.old_height_cm,
        inseam_cm=req.old_inseam_cm,
        riding_posture=req.old_riding_posture,
        usage=req.old_usage,
        desired_stack=req.old_desired_stack,
        desired_reach=req.old_desired_reach,
        desired_head_angle=req.old_desired_head_angle,
        desired_seat_angle=req.old_desired_seat_angle,
        desired_wheelbase=req.old_desired_wheelbase,
        notes=req.old_notes,
    )
    new_spec = GeometryChangeSpecSnapshot(
        height_cm=req.new_height_cm,
        inseam_cm=req.new_inseam_cm,
        riding_posture=req.new_riding_posture,
        usage=req.new_usage,
        desired_stack=req.new_desired_stack,
        desired_reach=req.new_desired_reach,
        desired_head_angle=req.new_desired_head_angle,
        desired_seat_angle=req.new_desired_seat_angle,
        desired_wheelbase=req.new_desired_wheelbase,
        notes=req.new_notes,
    )
    out = GeometryChangeRequestOut.model_validate(req)
    out.old_spec = old_spec
    out.new_spec = new_spec
    return out


def _invalidate_pending_changes(db: Session, order_id: int):
    pending = (
        db.query(GeometryChangeRequest)
        .filter(
            GeometryChangeRequest.order_id == order_id,
            GeometryChangeRequest.status == ChangeReviewStatus.pending,
        )
        .all()
    )
    for p in pending:
        p.status = ChangeReviewStatus.superseded


def _clear_schedules(db: Session, order_id: int) -> list[ProductionSchedule]:
    schedules = (
        db.query(ProductionSchedule)
        .filter(ProductionSchedule.order_id == order_id)
        .all()
    )
    cleared = []
    for s in schedules:
        db.delete(s)
        cleared.append(s)
    return cleared


@router.post("/{order_id}", response_model=GeometryChangeRequestOut, status_code=201)
def request_change(
    order_id: int,
    payload: GeometryChangeRequestCreate,
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    if order.status == OrderStatus.assembly_ready:
        raise HTTPException(
            400,
            f"当前订单状态为「{STATUS_LABELS.get(order.status.value, order.status.value)}」，"
            f"已装配完成，不能再发起几何参数变更。",
        )

    change_types = _detect_change_types(payload)
    if not change_types:
        raise HTTPException(400, "至少需要指定一项几何参数变更内容")

    spec = order.spec
    if not spec:
        raise HTTPException(400, "订单缺少客户规格数据，无法执行变更")

    requires_review = PRINTING_CHANGE_REVIEW_REQUIRED and (
        order.status == OrderStatus.printing
        or order.status == OrderStatus.inspecting
    )

    _invalidate_pending_changes(db, order_id)

    req = GeometryChangeRequest(
        order_id=order_id,
        change_types=",".join(change_types),
        reason=payload.reason,
        requested_by=payload.requested_by,
        old_height_cm=spec.height_cm,
        new_height_cm=payload.new_height_cm if payload.new_height_cm is not None else spec.height_cm,
        old_inseam_cm=spec.inseam_cm,
        new_inseam_cm=payload.new_inseam_cm if payload.new_inseam_cm is not None else spec.inseam_cm,
        old_riding_posture=spec.riding_posture,
        new_riding_posture=payload.new_riding_posture if payload.new_riding_posture is not None else spec.riding_posture,
        old_usage=spec.usage,
        new_usage=payload.new_usage if payload.new_usage is not None else spec.usage,
        old_notes=spec.notes,
        new_notes=payload.new_notes if payload.new_notes is not None else spec.notes,
        old_desired_stack=spec.desired_stack,
        new_desired_stack=payload.new_desired_stack if payload.new_desired_stack is not None else spec.desired_stack,
        old_desired_reach=spec.desired_reach,
        new_desired_reach=payload.new_desired_reach if payload.new_desired_reach is not None else spec.desired_reach,
        old_desired_head_angle=spec.desired_head_angle,
        new_desired_head_angle=payload.new_desired_head_angle if payload.new_desired_head_angle is not None else spec.desired_head_angle,
        old_desired_seat_angle=spec.desired_seat_angle,
        new_desired_seat_angle=payload.new_desired_seat_angle if payload.new_desired_seat_angle is not None else spec.desired_seat_angle,
        old_desired_wheelbase=spec.desired_wheelbase,
        new_desired_wheelbase=payload.new_desired_wheelbase if payload.new_desired_wheelbase is not None else spec.desired_wheelbase,
        requires_review=requires_review,
        delivery_delay_hours=DEFAULT_RECONFIRM_DELAY_HOURS,
    )
    db.add(req)
    db.flush()

    type_labels = [CHANGE_TYPE_LABELS.get(t, t) for t in change_types]

    if requires_review:
        status_remark = (
            f"客户发起几何参数变更（{'、'.join(type_labels)}），"
            f"原因：{payload.reason}。当前订单处于生产阶段，需走评审流程并重新排程。"
        )
        db.flush()
    else:
        spec.height_cm = req.new_height_cm
        spec.inseam_cm = req.new_inseam_cm
        spec.riding_posture = req.new_riding_posture
        spec.usage = req.new_usage
        spec.notes = req.new_notes
        spec.desired_stack = req.new_desired_stack
        spec.desired_reach = req.new_desired_reach
        spec.desired_head_angle = req.new_desired_head_angle
        spec.desired_seat_angle = req.new_desired_seat_angle
        spec.desired_wheelbase = req.new_desired_wheelbase

        if order.confirmation:
            for c in order.confirmation_list:
                c.is_active = False

        schedules_cleared = _clear_schedules(db, order_id)
        if schedules_cleared:
            req.schedules_cleared = True
            equip_names = list({s.equipment.name for s in schedules_cleared if s.equipment})
            schedule_msg = f"，已取消排产占用（设备：{'、'.join(equip_names)}）"
        else:
            schedule_msg = ""

        from_status = order.status
        order.status = OrderStatus.change_pending
        order.change_count += 1
        req.status = ChangeReviewStatus.approved
        req.reviewed_at = datetime.utcnow()

        status_remark = (
            f"几何参数变更（{'、'.join(type_labels)}）已生效：{payload.reason}"
            f"{schedule_msg}。"
            f"工程师需重新确认车架尺寸、管壁厚度、节点强度和目标重量。"
        )
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=OrderStatus.change_pending,
            operator=payload.requested_by,
            remark=status_remark,
        )
        db.add(history)

    db.commit()
    db.refresh(req)
    return _build_change_request_out(req)


@router.post("/{change_id}/review", response_model=GeometryChangeRequestOut)
def review_change_request(
    change_id: int,
    payload: ChangeReview,
    db: Session = Depends(get_db),
):
    req = (
        db.query(GeometryChangeRequest)
        .filter(GeometryChangeRequest.id == change_id)
        .first()
    )
    if not req:
        raise HTTPException(404, "变更申请不存在")
    if req.status != ChangeReviewStatus.pending:
        raise HTTPException(
            400,
            f"当前申请状态为「{CHANGE_REVIEW_STATUS_LABELS.get(req.status.value, req.status.value)}」，"
            f"无需重复评审",
        )

    order = db.query(Order).filter(Order.id == req.order_id).first()
    if not order:
        raise HTTPException(404, "关联订单不存在")

    req.reviewer_name = payload.reviewer_name
    req.review_remark = payload.review_remark
    req.reviewed_at = datetime.utcnow()

    type_labels = [CHANGE_TYPE_LABELS.get(t, t) for t in req.change_types.split(",")]

    if payload.approved:
        req.status = ChangeReviewStatus.approved
        if payload.estimated_delay_hours:
            req.delivery_delay_hours = payload.estimated_delay_hours

        spec = order.spec
        if spec:
            spec.height_cm = req.new_height_cm
            spec.inseam_cm = req.new_inseam_cm
            spec.riding_posture = req.new_riding_posture
            spec.usage = req.new_usage
            spec.notes = req.new_notes
            spec.desired_stack = req.new_desired_stack
            spec.desired_reach = req.new_desired_reach
            spec.desired_head_angle = req.new_desired_head_angle
            spec.desired_seat_angle = req.new_desired_seat_angle
            spec.desired_wheelbase = req.new_desired_wheelbase

        if order.confirmation:
            for c in order.confirmation_list:
                c.is_active = False

        schedules_cleared = _clear_schedules(db, order_id=order.id)
        if schedules_cleared:
            req.schedules_cleared = True

        from_status = order.status
        order.status = OrderStatus.change_pending
        order.change_count += 1

        delay_msg = (
            f"预计额外增加交付周期 {payload.estimated_delay_hours} 小时。"
            if payload.estimated_delay_hours else ""
        )
        cleared_msg = "、已取消原排产并释放设备占用" if schedules_cleared else ""
        history_remark = (
            f"几何参数变更评审通过（{'、'.join(type_labels)}）：{req.reason}。"
            f"评审意见：{payload.review_remark or '无'}{cleared_msg}。{delay_msg}"
            f"工程师需重新确认车架尺寸、管壁厚度、节点强度和目标重量后再排程。"
        )
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=OrderStatus.change_pending,
            operator=payload.reviewer_name,
            remark=history_remark,
        )
        db.add(history)
    else:
        req.status = ChangeReviewStatus.rejected
        history_remark = (
            f"几何参数变更申请被驳回（{'、'.join(type_labels)}）：{req.reason}。"
            f"评审意见：{payload.review_remark or '未提供'}"
        )
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=order.status,
            to_status=order.status,
            operator=payload.reviewer_name,
            remark=history_remark,
        )
        db.add(history)

    db.commit()
    db.refresh(req)
    return _build_change_request_out(req)


@router.get("/order/{order_id}", response_model=list[GeometryChangeRequestOut])
def get_order_change_requests(
    order_id: int,
    status: ChangeReviewStatus | None = None,
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    q = db.query(GeometryChangeRequest).filter(GeometryChangeRequest.order_id == order_id)
    if status:
        q = q.filter(GeometryChangeRequest.status == status)
    reqs = q.order_by(GeometryChangeRequest.created_at.desc()).all()
    return [_build_change_request_out(r) for r in reqs]


@router.get("/{change_id}", response_model=GeometryChangeRequestOut)
def get_change_request(change_id: int, db: Session = Depends(get_db)):
    req = (
        db.query(GeometryChangeRequest)
        .filter(GeometryChangeRequest.id == change_id)
        .first()
    )
    if not req:
        raise HTTPException(404, "变更申请不存在")
    return _build_change_request_out(req)


@router.get(
    "/order/{order_id}/summary",
    response_model=OrderChangeSummaryOut,
)
def get_order_change_summary(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "订单不存在")

    all_reqs = (
        db.query(GeometryChangeRequest)
        .filter(GeometryChangeRequest.order_id == order_id)
        .all()
    )
    total_delay = sum(r.delivery_delay_hours for r in all_reqs if r.status == ChangeReviewStatus.approved)
    last_change = max((r.created_at for r in all_reqs), default=None)

    pending_req = (
        db.query(GeometryChangeRequest)
        .filter(
            GeometryChangeRequest.order_id == order_id,
            GeometryChangeRequest.status == ChangeReviewStatus.pending,
        )
        .order_by(GeometryChangeRequest.created_at.desc())
        .first()
    )

    return OrderChangeSummaryOut(
        order_id=order_id,
        change_count=order.change_count,
        total_delay_hours=total_delay,
        last_change_at=last_change,
        pending_change_request=_build_change_request_out(pending_req) if pending_req else None,
    )


@router.get("/", response_model=list[GeometryChangeRequestOut])
def list_change_requests(
    status: ChangeReviewStatus | None = None,
    requires_review: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(GeometryChangeRequest)
    if status:
        q = q.filter(GeometryChangeRequest.status == status)
    if requires_review is not None:
        q = q.filter(GeometryChangeRequest.requires_review == requires_review)
    reqs = q.order_by(GeometryChangeRequest.created_at.desc()).offset(skip).limit(limit).all()
    return [_build_change_request_out(r) for r in reqs]
