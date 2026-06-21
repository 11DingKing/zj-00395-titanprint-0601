from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import (
    OrderStatus, RidingPosture, UsageType, InspectionResult,
    PowderBatchStatus, ReworkPriority, ChangeReviewStatus, ChangeType,
)


class CustomerSpecCreate(BaseModel):
    height_cm: float = Field(..., gt=0)
    inseam_cm: float = Field(..., gt=0)
    riding_posture: RidingPosture
    usage: UsageType
    desired_stack: Optional[float] = None
    desired_reach: Optional[float] = None
    desired_head_angle: Optional[float] = None
    desired_seat_angle: Optional[float] = None
    desired_wheelbase: Optional[float] = None
    notes: Optional[str] = None


class CustomerSpecOut(CustomerSpecCreate):
    id: int
    order_id: int

    model_config = {"from_attributes": True}


class EngineerConfirmationCreate(BaseModel):
    frame_size_label: str = Field(..., max_length=32)
    stack_mm: float = Field(..., gt=0)
    reach_mm: float = Field(..., gt=0)
    head_angle_deg: float
    seat_angle_deg: float
    chainstay_mm: float = Field(..., gt=0)
    wheelbase_mm: float = Field(..., gt=0)
    wall_thickness_mm: float = Field(..., gt=0)
    node_type: str = Field(..., max_length=64)
    target_weight_g: float = Field(..., gt=0)
    engineer_name: str = Field(..., max_length=128)
    remarks: Optional[str] = None


class EngineerConfirmationOut(EngineerConfirmationCreate):
    id: int
    order_id: int
    confirmed_at: datetime

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    customer_name: str = Field(..., max_length=128)
    customer_contact: str = Field(..., max_length=256)
    spec: CustomerSpecCreate


class OrderOut(BaseModel):
    id: int
    order_no: str
    customer_name: str
    customer_contact: str
    status: OrderStatus
    change_count: int
    created_at: datetime
    updated_at: datetime
    spec: Optional[CustomerSpecOut] = None
    confirmation: Optional[EngineerConfirmationOut] = None
    rework_priority: Optional[ReworkPriority] = None
    needs_batch_review: Optional[bool] = None
    powder_batch: Optional[str] = None

    model_config = {"from_attributes": True}


class OrderListOut(BaseModel):
    id: int
    order_no: str
    customer_name: str
    status: OrderStatus
    change_count: int
    created_at: datetime
    updated_at: datetime
    rework_priority: Optional[ReworkPriority] = None
    needs_batch_review: Optional[bool] = None
    powder_batch: Optional[str] = None

    model_config = {"from_attributes": True}


class StatusTransition(BaseModel):
    to_status: OrderStatus
    operator: Optional[str] = None
    remark: Optional[str] = None


class StatusHistoryOut(BaseModel):
    id: int
    order_id: int
    from_status: Optional[OrderStatus] = None
    to_status: OrderStatus
    operator: Optional[str] = None
    remark: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PrintEquipmentCreate(BaseModel):
    name: str = Field(..., max_length=128)
    model: Optional[str] = None
    build_volume_mm: Optional[str] = None
    max_temp_c: Optional[float] = None
    active: bool = True


class PrintEquipmentOut(PrintEquipmentCreate):
    id: int

    model_config = {"from_attributes": True}


class PowderBatchCreate(BaseModel):
    batch_no: str = Field(..., max_length=64)
    material: str = Field(..., max_length=64)
    manufacturer: str = Field(..., max_length=128)
    production_date: datetime
    expiry_date: datetime
    initial_weight_kg: float = Field(..., gt=0)
    remaining_weight_kg: float = Field(..., ge=0)
    status: PowderBatchStatus = PowderBatchStatus.normal
    recycling_count: int = Field(0, ge=0)
    max_recycling: int = Field(10, gt=0)
    heat_treat_window_low_c: Optional[float] = None
    heat_treat_window_high_c: Optional[float] = None
    anomaly_note: Optional[str] = None


class PowderBatchUpdate(BaseModel):
    material: Optional[str] = Field(None, max_length=64)
    manufacturer: Optional[str] = Field(None, max_length=128)
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    initial_weight_kg: Optional[float] = Field(None, gt=0)
    remaining_weight_kg: Optional[float] = Field(None, ge=0)
    status: Optional[PowderBatchStatus] = None
    recycling_count: Optional[int] = Field(None, ge=0)
    max_recycling: Optional[int] = Field(None, gt=0)
    heat_treat_window_low_c: Optional[float] = None
    heat_treat_window_high_c: Optional[float] = None
    anomaly_note: Optional[str] = None


class PowderBatchOut(PowderBatchCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AffectedOrderOut(BaseModel):
    order_id: int
    order_no: str
    customer_name: str
    status: OrderStatus
    schedule_id: int
    print_start: datetime
    inspection_result: Optional[InspectionResult] = None
    rework_priority: Optional[ReworkPriority] = None
    needs_batch_review: Optional[bool] = None

    model_config = {"from_attributes": True}


class BatchAnomalyReport(BaseModel):
    batch_id: int
    batch_no: str
    affected_orders_count: int
    affected_orders: list[AffectedOrderOut]
    anomaly_note: Optional[str] = None


class ProductionScheduleCreate(BaseModel):
    equipment_id: int
    powder_batch_id: Optional[int] = None
    powder_batch: str = Field(..., max_length=64)
    recycling_count: int = Field(0, ge=0)
    heat_treat_window_low_c: Optional[float] = None
    heat_treat_window_high_c: Optional[float] = None
    print_start: datetime
    print_end: datetime
    heat_treat_start: Optional[datetime] = None
    heat_treat_end: Optional[datetime] = None
    print_duration_hours: Optional[float] = None


class ProductionScheduleOut(ProductionScheduleCreate):
    id: int
    order_id: int
    created_at: datetime
    powder_batch_info: Optional[PowderBatchOut] = None

    model_config = {"from_attributes": True}


class ScheduleConflictOut(BaseModel):
    conflicting_schedule_id: int
    conflicting_order_no: str
    print_start: datetime
    print_end: datetime


class BatchReviewUpdate(BaseModel):
    batch_review_completed: bool
    batch_review_note: Optional[str] = None
    batch_reviewed_by: str = Field(..., max_length=128)


class QualityInspectionCreate(BaseModel):
    stack_deviation_mm: Optional[float] = None
    reach_deviation_mm: Optional[float] = None
    head_angle_deviation_deg: Optional[float] = None
    seat_angle_deviation_deg: Optional[float] = None
    wall_thickness_deviation_mm: Optional[float] = None
    node_check: Optional[str] = Field(None, max_length=32)
    node_check_detail: Optional[str] = None
    node_check_result: Optional[InspectionResult] = None
    flaw_detection_method: Optional[str] = Field(None, max_length=64)
    flaw_detection_result: InspectionResult
    flaw_detection_detail: Optional[str] = None
    within_tolerance: bool
    rework_priority: Optional[ReworkPriority] = None
    repair_opinion: Optional[str] = None
    inspector: str = Field(..., max_length=128)


class QualityInspectionOut(QualityInspectionCreate):
    id: int
    order_id: int
    needs_batch_review: bool = False
    batch_review_completed: bool = False
    batch_review_note: Optional[str] = None
    batch_reviewed_by: Optional[str] = None
    batch_reviewed_at: Optional[datetime] = None
    inspected_at: datetime

    model_config = {"from_attributes": True}


class EquipmentUtilizationOut(BaseModel):
    equipment_id: int
    equipment_name: str
    total_scheduled_hours: float
    utilization_rate: float


class ReworkRateOut(BaseModel):
    equipment_id: int
    equipment_name: str
    total_orders: int
    rework_orders: int
    rework_rate: float


class DeliveryCycleOut(BaseModel):
    equipment_id: int
    equipment_name: str
    average_delivery_hours: Optional[float] = None
    order_count: int


class GeometryChangeRequestCreate(BaseModel):
    reason: str = Field(..., min_length=5)
    requested_by: str = Field(..., max_length=128)
    new_height_cm: Optional[float] = Field(None, gt=0)
    new_inseam_cm: Optional[float] = Field(None, gt=0)
    new_riding_posture: Optional[RidingPosture] = None
    new_usage: Optional[UsageType] = None
    new_desired_stack: Optional[float] = None
    new_desired_reach: Optional[float] = None
    new_desired_head_angle: Optional[float] = None
    new_desired_seat_angle: Optional[float] = None
    new_desired_wheelbase: Optional[float] = None
    new_notes: Optional[str] = None


class GeometryChangeSpecSnapshot(BaseModel):
    height_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    riding_posture: Optional[RidingPosture] = None
    usage: Optional[UsageType] = None
    desired_stack: Optional[float] = None
    desired_reach: Optional[float] = None
    desired_head_angle: Optional[float] = None
    desired_seat_angle: Optional[float] = None
    desired_wheelbase: Optional[float] = None
    notes: Optional[str] = None


class GeometryChangeRequestOut(BaseModel):
    id: int
    order_id: int
    change_types: str
    reason: str
    requested_by: str
    old_spec: GeometryChangeSpecSnapshot | None = None
    new_spec: GeometryChangeSpecSnapshot | None = None
    status: ChangeReviewStatus
    requires_review: bool
    reviewer_name: Optional[str] = None
    review_remark: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    schedules_cleared: bool
    delivery_delay_hours: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChangeReview(BaseModel):
    approved: bool
    reviewer_name: str = Field(..., max_length=128)
    review_remark: Optional[str] = None
    estimated_delay_hours: Optional[float] = Field(0, ge=0)


class EngineerConfirmationUpdate(BaseModel):
    frame_size_label: str = Field(..., max_length=32)
    stack_mm: float = Field(..., gt=0)
    reach_mm: float = Field(..., gt=0)
    head_angle_deg: float
    seat_angle_deg: float
    chainstay_mm: float = Field(..., gt=0)
    wheelbase_mm: float = Field(..., gt=0)
    wall_thickness_mm: float = Field(..., gt=0)
    node_type: str = Field(..., max_length=64)
    node_strength_rating: Optional[str] = Field(None, max_length=32)
    target_weight_g: float = Field(..., gt=0)
    engineer_name: str = Field(..., max_length=128)
    remarks: Optional[str] = None


class EngineerConfirmationHistoryOut(BaseModel):
    id: int
    order_id: int
    version: int
    is_active: bool
    change_request_id: Optional[int] = None
    frame_size_label: str
    stack_mm: float
    reach_mm: float
    head_angle_deg: float
    seat_angle_deg: float
    chainstay_mm: float
    wheelbase_mm: float
    wall_thickness_mm: float
    node_type: str
    node_strength_rating: Optional[str] = None
    target_weight_g: float
    engineer_name: str
    confirmed_at: datetime
    remarks: Optional[str] = None

    model_config = {"from_attributes": True}


class OrderChangeSummaryOut(BaseModel):
    order_id: int
    change_count: int
    total_delay_hours: float
    last_change_at: Optional[datetime] = None
    pending_change_request: Optional[GeometryChangeRequestOut] = None


class DeliveryCycleDetailOut(BaseModel):
    equipment_id: int
    equipment_name: str
    average_delivery_hours: Optional[float] = None
    average_delivery_with_changes_hours: Optional[float] = None
    average_delay_from_changes_hours: Optional[float] = None
    change_affected_orders: int
    order_count: int
