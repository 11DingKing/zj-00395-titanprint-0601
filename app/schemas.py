from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import (
    OrderStatus, RidingPosture, UsageType, InspectionResult,
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
    created_at: datetime
    updated_at: datetime
    spec: Optional[CustomerSpecOut] = None
    confirmation: Optional[EngineerConfirmationOut] = None

    model_config = {"from_attributes": True}


class OrderListOut(BaseModel):
    id: int
    order_no: str
    customer_name: str
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

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


class ProductionScheduleCreate(BaseModel):
    equipment_id: int
    powder_batch: str = Field(..., max_length=64)
    print_start: datetime
    print_end: datetime
    heat_treat_start: Optional[datetime] = None
    heat_treat_end: Optional[datetime] = None
    print_duration_hours: Optional[float] = None


class ProductionScheduleOut(ProductionScheduleCreate):
    id: int
    order_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleConflictOut(BaseModel):
    conflicting_schedule_id: int
    conflicting_order_no: str
    print_start: datetime
    print_end: datetime


class QualityInspectionCreate(BaseModel):
    stack_deviation_mm: Optional[float] = None
    reach_deviation_mm: Optional[float] = None
    head_angle_deviation_deg: Optional[float] = None
    seat_angle_deviation_deg: Optional[float] = None
    wall_thickness_deviation_mm: Optional[float] = None
    node_check: Optional[str] = Field(None, max_length=32)
    node_check_detail: Optional[str] = None
    flaw_detection_method: Optional[str] = Field(None, max_length=64)
    flaw_detection_result: InspectionResult
    flaw_detection_detail: Optional[str] = None
    within_tolerance: bool
    repair_opinion: Optional[str] = None
    inspector: str = Field(..., max_length=128)


class QualityInspectionOut(QualityInspectionCreate):
    id: int
    order_id: int
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
