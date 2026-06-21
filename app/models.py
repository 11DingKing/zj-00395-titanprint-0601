import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, Float, String, Text, DateTime, ForeignKey, Enum, Boolean,
)
from sqlalchemy.orm import relationship

from app.database import Base


class OrderStatus(str, enum.Enum):
    pending = "pending"
    scheduled = "scheduled"
    printing = "printing"
    inspecting = "inspecting"
    rework = "rework"
    assembly_ready = "assembly_ready"


class PowderBatchStatus(str, enum.Enum):
    normal = "normal"
    warning = "warning"
    quarantined = "quarantined"
    depleted = "depleted"


class ReworkPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class RidingPosture(str, enum.Enum):
    road = "road"
    gravel = "gravel"
    time_trial = "time_trial"
    endurance = "endurance"
    track = "track"


class UsageType(str, enum.Enum):
    racing = "racing"
    recreational = "recreational"
    commuting = "commuting"
    touring = "touring"
    track_day = "track_day"


class InspectionResult(str, enum.Enum):
    pass_ = "pass"
    fail = "fail"
    conditional = "conditional"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)
    customer_name = Column(String(128), nullable=False)
    customer_contact = Column(String(256), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    spec = relationship("CustomerSpec", back_populates="order", uselist=False, cascade="all, delete-orphan")
    confirmation = relationship("EngineerConfirmation", back_populates="order", uselist=False, cascade="all, delete-orphan")
    schedules = relationship("ProductionSchedule", back_populates="order", cascade="all, delete-orphan")
    inspections = relationship("QualityInspection", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")


class CustomerSpec(Base):
    __tablename__ = "customer_specs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)

    height_cm = Column(Float, nullable=False)
    inseam_cm = Column(Float, nullable=False)
    riding_posture = Column(Enum(RidingPosture), nullable=False)
    usage = Column(Enum(UsageType), nullable=False)

    desired_stack = Column(Float)
    desired_reach = Column(Float)
    desired_head_angle = Column(Float)
    desired_seat_angle = Column(Float)
    desired_wheelbase = Column(Float)
    notes = Column(Text)

    order = relationship("Order", back_populates="spec")


class EngineerConfirmation(Base):
    __tablename__ = "engineer_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)

    frame_size_label = Column(String(32), nullable=False)
    stack_mm = Column(Float, nullable=False)
    reach_mm = Column(Float, nullable=False)
    head_angle_deg = Column(Float, nullable=False)
    seat_angle_deg = Column(Float, nullable=False)
    chainstay_mm = Column(Float, nullable=False)
    wheelbase_mm = Column(Float, nullable=False)

    wall_thickness_mm = Column(Float, nullable=False)
    node_type = Column(String(64), nullable=False)
    target_weight_g = Column(Float, nullable=False)

    engineer_name = Column(String(128), nullable=False)
    confirmed_at = Column(DateTime, default=datetime.utcnow)
    remarks = Column(Text)

    order = relationship("Order", back_populates="confirmation")


class PowderBatch(Base):
    __tablename__ = "powder_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_no = Column(String(64), unique=True, nullable=False, index=True)
    material = Column(String(64), nullable=False)
    manufacturer = Column(String(128), nullable=False)
    production_date = Column(DateTime, nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    initial_weight_kg = Column(Float, nullable=False)
    remaining_weight_kg = Column(Float, nullable=False)
    status = Column(Enum(PowderBatchStatus), default=PowderBatchStatus.normal, nullable=False, index=True)
    recycling_count = Column(Integer, default=0, nullable=False)
    max_recycling = Column(Integer, default=10, nullable=False)
    heat_treat_window_low_c = Column(Float)
    heat_treat_window_high_c = Column(Float)
    anomaly_note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schedules = relationship("ProductionSchedule", back_populates="powder_batch_ref")


class PrintEquipment(Base):
    __tablename__ = "print_equipment"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True)
    model = Column(String(128))
    build_volume_mm = Column(String(64))
    max_temp_c = Column(Float)
    active = Column(Boolean, default=True)

    schedules = relationship("ProductionSchedule", back_populates="equipment")


class ProductionSchedule(Base):
    __tablename__ = "production_schedules"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("print_equipment.id"), nullable=False)
    powder_batch_id = Column(Integer, ForeignKey("powder_batches.id"), index=True)

    powder_batch = Column(String(64), nullable=False)
    recycling_count = Column(Integer, default=0, nullable=False)
    heat_treat_window_low_c = Column(Float)
    heat_treat_window_high_c = Column(Float)
    print_start = Column(DateTime, nullable=False)
    print_end = Column(DateTime, nullable=False)
    heat_treat_start = Column(DateTime)
    heat_treat_end = Column(DateTime)
    print_duration_hours = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="schedules")
    equipment = relationship("PrintEquipment", back_populates="schedules")
    powder_batch_ref = relationship("PowderBatch", back_populates="schedules")


class QualityInspection(Base):
    __tablename__ = "quality_inspections"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)

    stack_deviation_mm = Column(Float)
    reach_deviation_mm = Column(Float)
    head_angle_deviation_deg = Column(Float)
    seat_angle_deviation_deg = Column(Float)
    wall_thickness_deviation_mm = Column(Float)

    node_check = Column(String(32))
    node_check_detail = Column(Text)
    node_check_result = Column(Enum(InspectionResult))

    flaw_detection_method = Column(String(64))
    flaw_detection_result = Column(Enum(InspectionResult), nullable=False)
    flaw_detection_detail = Column(Text)

    within_tolerance = Column(Boolean, nullable=False)
    rework_priority = Column(Enum(ReworkPriority))
    needs_batch_review = Column(Boolean, default=False)
    batch_review_completed = Column(Boolean, default=False)
    batch_review_note = Column(Text)
    batch_reviewed_by = Column(String(128))
    batch_reviewed_at = Column(DateTime)

    repair_opinion = Column(Text)
    inspector = Column(String(128), nullable=False)
    inspected_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="inspections")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    from_status = Column(Enum(OrderStatus), nullable=True)
    to_status = Column(Enum(OrderStatus), nullable=False)
    operator = Column(String(128))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="status_history")
