from datetime import datetime, timedelta

from app.database import SessionLocal, engine, Base
from app.models import (
    PrintEquipment, Order, CustomerSpec, EngineerConfirmation,
    ProductionSchedule, QualityInspection, OrderStatusHistory, OrderStatus,
    RidingPosture, UsageType, InspectionResult, PowderBatch,
    PowderBatchStatus, ReworkPriority,
)


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(PrintEquipment).count() > 0:
        db.close()
        return

    eq1 = PrintEquipment(name="EBM-A1", model="Arcam Q20plus", build_volume_mm="350×350×420", max_temp_c=1100, active=True)
    eq2 = PrintEquipment(name="SLM-B2", model="EOS M 290", build_volume_mm="250×250×325", max_temp_c=800, active=True)
    eq3 = PrintEquipment(name="DMLS-C3", model="Concept Laser XLINE", build_volume_mm="600×400×500", max_temp_c=1000, active=False)
    db.add_all([eq1, eq2, eq3])
    db.flush()

    now = datetime.utcnow()

    pb1 = PowderBatch(
        batch_no="Ti64-2026A",
        material="Ti-6Al-4V ELI",
        manufacturer="ATI Powder Metals",
        production_date=now - timedelta(days=30),
        expiry_date=now + timedelta(days=335),
        initial_weight_kg=50.0,
        remaining_weight_kg=35.5,
        status=PowderBatchStatus.normal,
        recycling_count=2,
        max_recycling=10,
        heat_treat_window_low_c=920.0,
        heat_treat_window_high_c=960.0,
    )
    pb2 = PowderBatch(
        batch_no="Ti64-2026B",
        material="Ti-6Al-4V ELI",
        manufacturer="ATI Powder Metals",
        production_date=now - timedelta(days=60),
        expiry_date=now + timedelta(days=305),
        initial_weight_kg=50.0,
        remaining_weight_kg=42.0,
        status=PowderBatchStatus.normal,
        recycling_count=1,
        max_recycling=10,
        heat_treat_window_low_c=920.0,
        heat_treat_window_high_c=960.0,
    )
    pb3 = PowderBatch(
        batch_no="Ti64-2026C",
        material="Ti-6Al-4V ELI",
        manufacturer="Carpenter Technology",
        production_date=now - timedelta(days=10),
        expiry_date=now + timedelta(days=355),
        initial_weight_kg=50.0,
        remaining_weight_kg=50.0,
        status=PowderBatchStatus.normal,
        recycling_count=0,
        max_recycling=10,
        heat_treat_window_low_c=920.0,
        heat_treat_window_high_c=960.0,
    )
    db.add_all([pb1, pb2, pb3])
    db.flush()

    orders_data = [
        ("张三", "zhangsan@example.com", 175, 82, RidingPosture.road, UsageType.racing, pb1),
        ("李四", "lisi@example.com", 182, 88, RidingPosture.endurance, UsageType.recreational, pb1),
        ("王五", "wangwu@example.com", 168, 76, RidingPosture.gravel, UsageType.touring, pb2),
        ("赵六", "zhaoliu@example.com", 170, 80, RidingPosture.road, UsageType.racing, pb2),
        ("孙七", "sunqi@example.com", 185, 90, RidingPosture.time_trial, UsageType.racing, pb3),
    ]

    for i, (name, contact, height, inseam, posture, usage, powder_batch) in enumerate(orders_data):
        order = Order(
            order_no=f"TP-DEMO-{i+1:03d}",
            customer_name=name,
            customer_contact=contact,
            status=OrderStatus.pending,
        )
        db.add(order)
        db.flush()

        spec = CustomerSpec(
            order_id=order.id,
            height_cm=height,
            inseam_cm=inseam,
            riding_posture=posture,
            usage=usage,
            desired_stack=540 + i * 5,
            desired_reach=380 + i * 3,
            desired_head_angle=73.0,
            desired_seat_angle=73.5,
        )
        db.add(spec)

        history = OrderStatusHistory(
            order_id=order.id, from_status=None, to_status=OrderStatus.pending, remark="种子数据创建"
        )
        db.add(history)

    db.commit()

    order1 = db.query(Order).filter(Order.order_no == "TP-DEMO-001").first()
    order2 = db.query(Order).filter(Order.order_no == "TP-DEMO-002").first()

    conf1 = EngineerConfirmation(
        order_id=order1.id,
        frame_size_label="M",
        stack_mm=545,
        reach_mm=382,
        head_angle_deg=73.0,
        seat_angle_deg=73.5,
        chainstay_mm=410,
        wheelbase_mm=985,
        wall_thickness_mm=1.2,
        node_type="一体成型",
        target_weight_g=1350,
        engineer_name="陈工",
        remarks="标准公路几何",
    )
    db.add(conf1)

    history1 = OrderStatusHistory(
        order_id=order1.id,
        from_status=OrderStatus.pending,
        to_status=OrderStatus.scheduled,
        operator="陈工",
        remark="已确认车架参数",
    )
    db.add(history1)
    order1.status = OrderStatus.scheduled

    sched1 = ProductionSchedule(
        order_id=order1.id,
        equipment_id=eq1.id,
        powder_batch_id=pb1.id,
        powder_batch="Ti64-2026A",
        recycling_count=pb1.recycling_count,
        heat_treat_window_low_c=pb1.heat_treat_window_low_c,
        heat_treat_window_high_c=pb1.heat_treat_window_high_c,
        print_start=now + timedelta(hours=2),
        print_end=now + timedelta(hours=14),
        heat_treat_start=now + timedelta(hours=16),
        heat_treat_end=now + timedelta(hours=24),
        print_duration_hours=12.0,
    )
    db.add(sched1)

    order3 = db.query(Order).filter(Order.order_no == "TP-DEMO-003").first()
    order4 = db.query(Order).filter(Order.order_no == "TP-DEMO-004").first()

    conf3 = EngineerConfirmation(
        order_id=order3.id,
        frame_size_label="S",
        stack_mm=530,
        reach_mm=375,
        head_angle_deg=72.0,
        seat_angle_deg=73.0,
        chainstay_mm=405,
        wheelbase_mm=980,
        wall_thickness_mm=1.2,
        node_type="一体成型",
        target_weight_g=1300,
        engineer_name="陈工",
        remarks="Gravel几何，加强型节点",
    )
    db.add(conf3)

    sched2 = ProductionSchedule(
        order_id=order2.id,
        equipment_id=eq2.id,
        powder_batch_id=pb1.id,
        powder_batch="Ti64-2026A",
        recycling_count=pb1.recycling_count,
        heat_treat_window_low_c=pb1.heat_treat_window_low_c,
        heat_treat_window_high_c=pb1.heat_treat_window_high_c,
        print_start=now + timedelta(hours=1),
        print_end=now + timedelta(hours=13),
        heat_treat_start=now + timedelta(hours=15),
        heat_treat_end=now + timedelta(hours=23),
        print_duration_hours=12.0,
    )
    db.add(sched2)

    sched3 = ProductionSchedule(
        order_id=order3.id,
        equipment_id=eq1.id,
        powder_batch_id=pb2.id,
        powder_batch="Ti64-2026B",
        recycling_count=pb2.recycling_count,
        heat_treat_window_low_c=pb2.heat_treat_window_low_c,
        heat_treat_window_high_c=pb2.heat_treat_window_high_c,
        print_start=now + timedelta(hours=16),
        print_end=now + timedelta(hours=28),
        print_duration_hours=12.0,
    )
    db.add(sched3)

    db.commit()

    history2 = OrderStatusHistory(
        order_id=order1.id,
        from_status=OrderStatus.scheduled,
        to_status=OrderStatus.printing,
        operator="系统",
        remark="打印开始",
    )
    db.add(history2)
    order1.status = OrderStatus.printing

    history3 = OrderStatusHistory(
        order_id=order1.id,
        from_status=OrderStatus.printing,
        to_status=OrderStatus.inspecting,
        operator="质检员赵",
        remark="打印完成，进入质检",
    )
    db.add(history3)
    order1.status = OrderStatus.inspecting

    db.commit()

    insp1 = QualityInspection(
        order_id=order1.id,
        stack_deviation_mm=0.3,
        reach_deviation_mm=0.2,
        head_angle_deviation_deg=0.1,
        seat_angle_deviation_deg=0.05,
        wall_thickness_deviation_mm=0.05,
        node_check="合格",
        node_check_detail="所有连接节点无裂纹、气孔",
        node_check_result=InspectionResult.pass_,
        flaw_detection_method="CT扫描",
        flaw_detection_result=InspectionResult.pass_,
        flaw_detection_detail="未发现内部缺陷",
        within_tolerance=True,
        rework_priority=ReworkPriority.low,
        inspector="赵质检",
    )
    db.add(insp1)

    db.commit()

    conf2 = EngineerConfirmation(
        order_id=order2.id,
        frame_size_label="L",
        stack_mm=560,
        reach_mm=395,
        head_angle_deg=72.5,
        seat_angle_deg=73.0,
        chainstay_mm=415,
        wheelbase_mm=1000,
        wall_thickness_mm=1.0,
        node_type="一体成型",
        target_weight_g=1400,
        engineer_name="陈工",
        remarks="耐力型几何，管壁减薄",
    )
    db.add(conf2)

    transitions = [
        (OrderStatus.pending, OrderStatus.scheduled),
        (OrderStatus.scheduled, OrderStatus.printing),
        (OrderStatus.printing, OrderStatus.inspecting),
    ]
    for from_s, to_s in transitions:
        history_n = OrderStatusHistory(
            order_id=order2.id,
            from_status=from_s,
            to_status=to_s,
            operator="系统",
        )
        db.add(history_n)

    order2.status = OrderStatus.inspecting

    insp2 = QualityInspection(
        order_id=order2.id,
        stack_deviation_mm=1.5,
        reach_deviation_mm=2.0,
        head_angle_deviation_deg=0.8,
        seat_angle_deviation_deg=0.3,
        wall_thickness_deviation_mm=0.2,
        node_check="不合格",
        node_check_detail="下管连接节点发现微裂纹",
        node_check_result=InspectionResult.fail,
        flaw_detection_method="CT扫描",
        flaw_detection_result=InspectionResult.fail,
        flaw_detection_detail="下管节点区域发现长度2.3mm裂纹，疑似粉末批次质量问题",
        within_tolerance=False,
        rework_priority=ReworkPriority.urgent,
        needs_batch_review=True,
        repair_opinion="需返修下管节点区域，补焊后重新探伤，建议核查同批次粉末其他订单",
        inspector="赵质检",
    )
    db.add(insp2)

    history_rework = OrderStatusHistory(
        order_id=order2.id,
        from_status=OrderStatus.inspecting,
        to_status=OrderStatus.rework,
        operator="赵质检",
        remark="尺寸偏差超标+节点裂纹，需返修，已触发粉末批次异常关联复核",
    )
    db.add(history_rework)
    order2.status = OrderStatus.rework

    pb1.status = PowderBatchStatus.warning
    pb1.anomaly_note = "订单 TP-DEMO-002 探伤检查不合格，怀疑粉末批次问题。探伤详情：下管节点区域发现长度2.3mm裂纹，疑似粉末批次质量问题"

    order3.status = OrderStatus.scheduled
    history_conf3 = OrderStatusHistory(
        order_id=order3.id,
        from_status=OrderStatus.pending,
        to_status=OrderStatus.scheduled,
        operator="陈工",
        remark="已确认车架参数",
    )
    db.add(history_conf3)

    conf4 = EngineerConfirmation(
        order_id=order4.id,
        frame_size_label="M",
        stack_mm=542,
        reach_mm=380,
        head_angle_deg=73.0,
        seat_angle_deg=73.5,
        chainstay_mm=410,
        wheelbase_mm=985,
        wall_thickness_mm=1.1,
        node_type="一体成型",
        target_weight_g=1320,
        engineer_name="陈工",
        remarks="竞赛级公路几何",
    )
    db.add(conf4)
    order4.status = OrderStatus.pending

    order5 = db.query(Order).filter(Order.order_no == "TP-DEMO-005").first()
    conf5 = EngineerConfirmation(
        order_id=order5.id,
        frame_size_label="XL",
        stack_mm=570,
        reach_mm=400,
        head_angle_deg=76.0,
        seat_angle_deg=75.0,
        chainstay_mm=405,
        wheelbase_mm=995,
        wall_thickness_mm=1.2,
        node_type="一体成型",
        target_weight_g=1450,
        engineer_name="陈工",
        remarks="计时赛激进几何",
    )
    db.add(conf5)
    order5.status = OrderStatus.pending

    db.commit()
    db.close()
    print("种子数据已创建")


if __name__ == "__main__":
    seed()
