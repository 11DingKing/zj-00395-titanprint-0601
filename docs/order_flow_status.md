# TitanPrint 订单流程现状说明

> 本文档基于项目已有代码逐行梳理，描述订单从"待确认"到"可装配"实际经过的状态、
> 设备冲突与质检结论对流程的影响点、以及统计模块的数据汇总来源。
> 供后续改粉末追踪功能时参考，避免凭业务描述重新设计。

---

## 一、订单状态枚举与中文标签

| 枚举值 | 中文标签 | 说明 |
|--------|----------|------|
| `pending` | 待确认 | 订单创建后的初始状态 |
| `change_pending` | 变更待确认 | 客户发起几何参数变更后等待工程师重新确认 |
| `scheduled` | 已排产 | 已分配设备与时间段 |
| `printing` | 打印中 | 设备开始打印 |
| `inspecting` | 质检中 | 打印完成，进入质量检验 |
| `rework` | 返修 | 质检不通过，需返修 |
| `assembly_ready` | 可装配 | 质检通过，车架可进入装配 |

定义位置：[models.py](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/models.py#L12-L19) `OrderStatus`
中文标签：[config.py](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/config.py#L15-L23) `STATUS_LABELS`

---

## 二、合法状态流转规则

定义位置：[config.py](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/config.py#L5-L13) `VALID_TRANSITIONS`

```
pending          → [scheduled, change_pending]
change_pending   → [pending, scheduled]
scheduled        → [printing, pending, change_pending]
printing         → [inspecting, change_pending]
inspecting       → [rework, assembly_ready]
rework           → [scheduled, inspecting, change_pending]
assembly_ready   → []  (终态，不可再流转)
```

> **注意**：`VALID_TRANSITIONS` 是手工维护的硬编码字典。
> 代码中实际流转操作可能绕过此校验（见下文各触发点），
> 两者存在微妙差异——代码实际流转更严格，并非 VALID_TRANSITIONS 中每条路径都有对应触发逻辑。

---

## 三、状态流转图

```
                          ┌─────────────────┐
                          │  客户发起几何变更  │
                          │ (非打印/质检阶段) │
                          └────────┬────────┘
                                   │ 自动通过
                                   ▼
┌──────────┐  工程师确认   ┌──────────────┐  创建排产   ┌──────────┐
│  待确认   │◄────────────│ 变更待确认    │            │          │
│ pending  │─────────────│change_pending│            │          │
└────┬─────┘  重新确认后   └──────┬───────┘            │          │
     │        回到pending         │                    │          │
     │                            │                    │          │
     │  创建排产(需有确认)         │ 创建排产(需有确认)  │          │
     ▼                            ▼                    │          │
┌──────────┐                  ┌──────────┐             │          │
│  已排产   │◄─────────────────│  已排产   │             │          │
│scheduled │                  │scheduled │             │          │
└────┬─────┘                  └────┬─────┘             │          │
     │                             │                   │          │
     │ 开始打印                     │ 开始打印           │          │
     ▼                             ▼                   │          │
┌──────────┐                  ┌──────────┐             │          │
│  打印中   │                  │  打印中   │             │          │
│printing  │                  │printing  │             │          │
└────┬─────┘                  └────┬─────┘             │          │
     │                             │                   │          │
     │ 完成打印                     │ 完成打印           │          │
     ▼                             ▼                   │          │
┌──────────┐                  ┌──────────┐             │          │
│  质检中   │                  │  质检中   │             │          │
│inspecting│                  │inspecting│             │          │
└──┬───┬───┘                  └──┬───┬───┘             │          │
   │   │                         │   │                 │          │
   │   │ 质检通过                 │   │ 质检不通过       │          │
   │   ▼                         │   ▼                 │          │
   │ ┌──────────┐                │ ┌──────────┐        │          │
   │ │ 可装配    │                │ │  返修     │        │          │
   │ │assembly  │                │ │ rework   │        │          │
   │ │ _ready   │                │ └────┬─────┘        │          │
   │ └──────────┘                │      │              │          │
   │  (终态)                     │      │ 重新排产      │          │
   │                             │      └──────┐       │          │
   │                             │             ▼       │          │
   │                             │      ┌──────────┐   │          │
   │                             │      │  已排产   │───┘          │
   │                             │      │scheduled │              │
   │                             │      └──────────┘              │
   │                             │                                 │
   │                             └─── 也可直接提交质检 ────────────┘
   │                                (rework → inspecting)

       ┌──────────────────────────────────────────────────────┐
       │            任意非终态 → 变更待确认 (几何变更)          │
       │                                                      │
       │  pending ──────→ change_pending (自动通过)            │
       │  scheduled ────→ change_pending (自动通过，清排产)    │
       │  printing ─────→ change_pending (需评审，清排产)      │
       │  inspecting ───→ change_pending (需评审，清排产)      │
       │  rework ───────→ change_pending (需评审，清排产)      │
       │  assembly_ready → 禁止变更                           │
       └──────────────────────────────────────────────────────┘
```

---

## 四、各状态流转触发点详述

### 4.1 pending（待确认）

**进入方式：**
1. 订单创建 → [orders.py:34-57](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/orders.py#L34-L57) `create_order`
2. 工程师首次确认（订单已在 pending 状态）→ 状态不变，记录确认 → [confirmations.py:41-99](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/confirmations.py#L41-L99) `create_confirmation`
3. 变更待确认后工程师重新确认 → change_pending → pending → [confirmations.py:73-86](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/confirmations.py#L73-L86)
4. 重新确认接口 → change_pending → pending → [confirmations.py:102-173](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/confirmations.py#L102-L173) `reconfirm_after_change`
5. 删除最后一条排产记录 → scheduled → pending → [schedules.py:197-226](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L197-L226) `delete_schedule`

**离开方式：**
- 创建排产 → scheduled（需有工程师确认记录）→ [schedules.py:44-155](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L44-L155) `create_schedule`
- 发起几何变更 → change_pending → [geometry_changes.py:105-222](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/geometry_changes.py#L105-L222) `request_change`

### 4.2 change_pending（变更待确认）

**进入方式：**
- 几何参数变更生效时进入（自动通过或评审通过）→ [geometry_changes.py:200-218](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/geometry_changes.py#L200-L218)

**进入时的副作用：**
- 已有工程师确认记录全部标记 `is_active=False`
- 已有排产记录全部删除（释放设备占用）
- 订单 `change_count += 1`
- 客户规格 (`CustomerSpec`) 立即更新为新值

**离开方式：**
- 工程师重新确认 → pending → [confirmations.py:102-173](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/confirmations.py#L102-L173)

### 4.3 scheduled（已排产）

**进入方式：**
- 创建排产记录 → [schedules.py:134-136](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L134-L136) `create_schedule`
  - 前置条件：订单有活跃的工程师确认 (`order.confirmation`)
  - 前置条件：订单状态为 `pending` 或 `rework`
  - 返修后重新排产走同一条路径

**离开方式：**
- 开始打印 → printing → [schedules.py:229-255](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L229-L255) `start_printing`
- 发起几何变更 → change_pending
- 删除最后排产 → pending

### 4.4 printing（打印中）

**进入方式：**
- `start_printing` → [schedules.py:229-255](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L229-L255)
  - 前置条件：订单状态为 `scheduled`

**离开方式：**
- 完成打印 → inspecting → [schedules.py:258-284](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L258-L284) `finish_printing`
- 发起几何变更（需评审）→ change_pending

### 4.5 inspecting（质检中）

**进入方式：**
- `finish_printing` → [schedules.py:258-284](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L258-L284)
- 从 `printing` 状态也可直接提交质检（允许提前质检）→ [inspections.py:21-26](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L21-L26)

**离开方式（质检结论决定）：**

| 质检结论 | 条件 | 目标状态 |
|---------|------|---------|
| 通过 | `within_tolerance=True` **且** `flaw_detection_result≠fail` | `assembly_ready` |
| 不通过 | `within_tolerance=False` **或** `flaw_detection_result=fail` | `rework` |

> 代码位置：[inspections.py:62-141](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L62-L141)

### 4.6 rework（返修）

**进入方式：**
- 质检不通过自动转入 → [inspections.py:127-128](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L127-L128)

**离开方式：**
- 重新排产 → scheduled（与首次排产走同一 `create_schedule` 接口）
- 直接提交质检 → inspecting（返修后重新质检）
- 发起几何变更 → change_pending

### 4.7 assembly_ready（可装配）

**进入方式：**
- 质检通过 → [inspections.py:140](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L140)
- 手动状态流转 → [orders.py:149-167](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/orders.py#L149-L167)
  - 额外校验：必须有质检记录，且该记录 `within_tolerance=True` 且 `flaw_detection_result≠fail`
  - 否则抛出 400 错误

**终态**：`assembly_ready` 无合法后续流转（`VALID_TRANSITIONS` 对应列表为空）。

---

## 五、设备冲突如何影响流程

冲突检测函数：[schedules.py:20-41](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L20-L41) `_check_conflicts`

### 5.1 冲突判定逻辑

对同一台设备（`equipment_id`），若新排产的 `[print_start, print_end)` 与已有排产的时间范围存在重叠，则判定冲突。

重叠条件（SQLAlchemy 过滤）：
```python
ProductionSchedule.print_start < end   # 已有排产开始早于新排产结束
AND
ProductionSchedule.print_end > start   # 已有排产结束晚于新排产开始
```

### 5.2 冲突发生时的行为

- **创建排产时冲突** → 返回 HTTP 409，响应体包含 `detail` 和 `conflicts` 列表
  - 代码位置：[schedules.py:107-115](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L107-L115)
  - 订单状态不会变更

- **冲突预检接口** → `GET /schedules/check-conflicts`
  - 代码位置：[schedules.py:158-165](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L158-L165)
  - 仅查询，不修改任何数据

### 5.3 几何变更释放设备占用

当几何参数变更被通过时，订单的所有排产记录被删除（`_clear_schedules`），释放设备占用。
- 代码位置：[geometry_changes.py:92-102](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/geometry_changes.py#L92-L102)

### 5.4 删除排产记录的回退

删除最后一条排产记录时，若订单仍处于 `scheduled` 状态，自动回退到 `pending`。
- 代码位置：[schedules.py:206-224](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L206-L224)

### 5.5 设备停用

`PrintEquipment.active=False` 时，排产接口拒绝使用该设备（返回 400）。
- 代码位置：[schedules.py:64-65](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L64-L65)

---

## 六、质检结论如何影响流程

质检创建接口：[inspections.py:15-154](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L15-L154) `create_inspection`

### 6.1 质检结论判定流程

```
                    ┌───────────────────────────┐
                    │     提交质检记录            │
                    └──────────┬────────────────┘
                               │
                    ┌──────────▼────────────────┐
                    │ within_tolerance=True ?    │
                    └───┬───────────────────┬───┘
                       YES                   NO
                        │                     │
                        │              ┌──────▼───────┐
                        │              │必须填写       │
                        │              │repair_opinion │
                        │              └──────┬───────┘
                        │                     │
               ┌────────▼──────────┐          │
               │flaw_detection     │          │
               │≠ fail ?           │          │
               └──┬────────────┬───┘          │
                 YES           NO             │
                  │             │              │
                  ▼             ▼              ▼
           ┌───────────┐  ┌───────────────────────┐
           │可装配      │  │返修 (rework)           │
           │assembly   │  │原因：尺寸超差/探伤不通过  │
           │_ready     │  └───────────┬───────────┘
           └───────────┘              │
                         ┌────────────▼────────────┐
                         │ 探伤失败时的额外处理：    │
                         │ 1. 粉末批次→warning     │
                         │ 2. 同批次订单→需复核     │
                         │ 3. 当前质检→urgent优先级 │
                         └─────────────────────────┘
```

### 6.2 质检通过条件（两个条件同时满足）

1. `within_tolerance = True` — 尺寸偏差在容差范围内
2. `flaw_detection_result ≠ fail` — 探伤检查未失败（`pass` 或 `conditional` 均可）

任一条件不满足 → 转入返修。

### 6.3 质检不通过 → 返修时的额外处理

当 `flaw_detection_result == fail` 时触发**粉末批次异常关联**逻辑：
- 代码位置：[inspections.py:64-125](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L64-L125)

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 查找关联粉末批次 | 通过排产记录的 `powder_batch_id` 或 `powder_batch`(batch_no) 查找 |
| 2 | 粉末批次状态 → `warning` | 不论之前是什么状态（非隔离的都升级） |
| 3 | 追加 `anomaly_note` | 在已有 `anomaly_note` 后追加本次探伤失败信息 |
| 4 | 当前质检记录标记 | `needs_batch_review=True`，`rework_priority=urgent` |
| 5 | 同批次其他订单 | 查找所有使用同一粉末批次的排产记录 |
| 6 | 其他订单的最近质检 | 标记 `needs_batch_review=True` |
| 7 | 其他订单优先级提升 | 若原优先级为 `low`/`medium`/`None`，提升为 `high` |

### 6.4 超出容差必须填写返修意见

- 代码位置：[inspections.py:51-53](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L51-L53)
- `within_tolerance=False` 时，若 `repair_opinion` 为空则返回 400 错误

### 6.5 手动流转到 assembly_ready 的额外校验

通过 `POST /orders/{id}/transition` 手动流转到 `assembly_ready` 时：
- 代码位置：[orders.py:149-167](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/orders.py#L149-L167)
- 必须存在质检记录
- 最近一次质检必须 `within_tolerance=True` 且 `flaw_detection_result≠fail`
- 否则抛出 400 错误

---

## 七、返修流程详述

### 7.1 进入返修

质检不通过时自动转入，无需手动操作。

### 7.2 返修后出路

| 路径 | 接口 | 说明 |
|------|------|------|
| 重新排产 → scheduled | `POST /schedules/{order_id}` | 需工程师确认记录仍有效；走同一 `create_schedule` 接口 |
| 直接质检 → inspecting | `POST /inspections/{order_id}` | 返修完成后直接提交质检 |
| 几何变更 → change_pending | `POST /geometry-changes/{order_id}` | 需评审通过 |

### 7.3 返修循环

一个订单可以多次经过 `质检→返修→排产→打印→质检` 循环。
每次质检都会创建新的 `QualityInspection` 记录，状态流转历史通过 `OrderStatusHistory` 完整保留。

---

## 八、统计模块数据汇总来源

统计接口文件：[analytics.py](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/analytics.py)

### 8.1 设备利用率 (`GET /analytics/equipment-utilization`)

| 数据项 | 来源表/字段 | 计算方式 |
|--------|------------|---------|
| 活跃设备列表 | `PrintEquipment` WHERE `active=True` | 全量查询 |
| 设备排产工时 | `ProductionSchedule.print_duration_hours` | `SUM` 按 `equipment_id` 分组，可按时间范围+粉末批次筛选 |
| 利用率 | 排产工时 / 总时间窗口 | `total_hours = end - start`，默认从最早排产记录到当前时间 |

代码位置：[analytics.py:19-66](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/analytics.py#L19-L66)

### 8.2 返修率 (`GET /analytics/rework-rate`)

| 数据项 | 来源表/字段 | 计算方式 |
|--------|------------|---------|
| 每台设备的总订单数 | `ProductionSchedule` → `Order` | 按设备筛选排产，取关联 `order_id` 去重计数 |
| 返修次数 | `OrderStatusHistory` WHERE `to_status=rework` | 按设备关联的 `order_id` 筛选，计数 `to_status=rework` 的记录数 |
| 返修率 | 返修次数 / 总订单数 | 按设备分组 |

> 注意：返修率统计的是**流转到 rework 状态的次数**，而非去重后的订单数。一个订单多次返修会多次计入。

代码位置：[analytics.py:69-124](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/analytics.py#L69-L124)

### 8.3 交付周期 (`GET /analytics/delivery-cycle`)

| 数据项 | 来源表/字段 | 计算方式 |
|--------|------------|---------|
| 订单创建时间 | `OrderStatusHistory.created_at` WHERE `to_status=pending` | 最早的 `to_status=pending` 记录时间 |
| 交付完成时间 | `OrderStatusHistory.created_at` WHERE `to_status=assembly_ready` | 最早的 `to_status=assembly_ready` 记录时间 |
| 平均交付周期 | 两者之差的平均值 | `(delivered - created)` 以小时为单位，按设备分组取平均 |

代码位置：[analytics.py:127-189](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/analytics.py#L127-L189)

### 8.4 交付周期明细 (`GET /analytics/delivery-cycle-detail`)

在交付周期基础上增加：

| 数据项 | 来源表/字段 | 计算方式 |
|--------|------------|---------|
| 变更影响订单数 | `Order.change_count > 0` | 统计有几何变更的订单数 |
| 变更导致延迟 | `GeometryChangeRequest.delivery_delay_hours` | `SUM` 已通过评审的变更请求延迟时长 |
| 含变更的平均交付周期 | 仅统计 `change_count > 0` 的订单 | 同交付周期计算方式 |
| 变更导致的平均延迟 | 变更延迟的平均值 | 按设备分组 |

代码位置：[analytics.py:192-286](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/analytics.py#L192-L286)

### 8.5 统计汇总的筛选条件

所有统计接口均支持以下筛选参数：
- `start` / `end` — 时间范围（基于排产记录的 print_start / print_end）
- `powder_batch_id` / `powder_no` — 按粉末批次筛选

### 8.6 数据来源关系图

```
PrintEquipment (active=True)
    │
    ├── ProductionSchedule (设备利用率、返修率、交付周期的设备维度)
    │       │
    │       ├── equipment_id ──→ PrintEquipment
    │       ├── order_id ──→ Order
    │       ├── powder_batch_id ──→ PowderBatch
    │       └── print_duration_hours ──→ 利用率计算
    │
    ├── Order (返修率、交付周期的订单维度)
    │       │
    │       └── change_count ──→ 变更影响判断
    │
    ├── OrderStatusHistory (返修率、交付周期的时间点)
    │       │
    │       ├── to_status=pending ──→ 订单创建时间
    │       ├── to_status=rework ──→ 返修次数
    │       └── to_status=assembly_ready ──→ 交付完成时间
    │
    └── GeometryChangeRequest (变更延迟)
            │
            └── delivery_delay_hours WHERE status=approved ──→ 延迟时长
```

---

## 九、粉末批次现有逻辑（改粉末追踪的参考点）

### 9.1 粉末批次状态枚举

| 枚举值 | 说明 | 对流程的影响 |
|--------|------|-------------|
| `normal` | 正常 | 无限制 |
| `warning` | 异常警告 | 排产时给出警告但**不阻止**；触发同批次订单 `needs_batch_review` |
| `quarantined` | 已隔离 | **禁止**用于新排产，返回 400 |
| `depleted` | 已耗尽 | 排产时给出警告但**不阻止** |

定义位置：[models.py:37-41](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/models.py#L37-L41) `PowderBatchStatus`

### 9.2 粉末批次对排产的影响

- 代码位置：[schedules.py:74-106](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/schedules.py#L74-L106)
- `quarantined` → 拒绝排产
- `warning` → 允许排产，追加警告到历史备注
- `depleted` → 允许排产，追加警告到历史备注
- `recycling_count >= max_recycling` → 允许排产，追加警告到历史备注
- `remaining_weight_kg <= 0` → 允许排产，追加警告到历史备注

### 9.3 质检探伤失败 → 粉末批次异常

- 代码位置：[inspections.py:64-125](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/inspections.py#L64-L125)
- 质检中 `flaw_detection_result=fail` → 关联粉末批次状态升级为 `warning`（非隔离）
- 同时标记同批次其他订单需要批次复核

### 9.4 手动标记异常

- 代码位置：[powder_batches.py:99-139](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/powder_batches.py#L99-L139) `mark_batch_anomaly`
- 可手动标记异常，默认自动隔离（`auto_quarantine=True`）
- 可自动标记关联订单需复核（`auto_flag_orders=True`）
- 关联订单的最近质检记录：`needs_batch_review=True`，`rework_priority=urgent`

### 9.5 批次复核

- 查询需复核的质检记录：[powder_batches.py:181-195](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/powder_batches.py#L181-L195) `get_order_batch_reviews`
- 完成复核：[powder_batches.py:198-216](file:///Users/huangding/Documents/SOLOCODE%203/0619/mbp/zj-00395-titanprint-5/app/routers/powder_batches.py#L198-L216) `update_batch_review`
- 复核完成后**不改变**订单状态，仅记录复核结果

### 9.6 当前粉末追踪的缺口（改追踪时的注意点）

1. **排产时粉末批次可为字符串** — `ProductionSchedule.powder_batch` 是自由文本字段，`powder_batch_id` 可为空。即使指定了 `powder_batch_id`，异常关联查找也会回退到字符串匹配。
2. **粉末使用量未扣减** — 排产时不从 `PowderBatch.remaining_weight_kg` 中扣减，仅做警告判断。
3. **回收次数未自增** — 排产时 `recycling_count` 由前端传入，排产完成后不自动更新 `PowderBatch` 的回收次数。
4. **批次复核不影响状态** — `batch_review_completed=True` 后，订单状态不变。没有"复核不通过→回退到返修"的自动逻辑。
5. **质检触发粉末异常只升级到 warning** — 不会自动隔离，需手动调用 `mark_batch_anomaly`。
6. **`_get_affected_orders` 只查 `powder_batch_id`** — 优先用 ID 查找，找不到才用 batch_no 字符串匹配。如果排产时只填了 `powder_batch` 字符串没填 `powder_batch_id`，关联查找可能遗漏。

---

## 十、关键数据表关系

```
orders
  ├── 1:1 ── customer_specs (客户规格)
  ├── 1:N ── engineer_confirmations (工程师确认，is_active 区分当前版本)
  ├── 1:N ── production_schedules (排产记录)
  │               ├── N:1 ── print_equipment (打印设备)
  │               └── N:1 ── powder_batches (粉末批次)
  ├── 1:N ── quality_inspections (质检记录)
  ├── 1:N ── order_status_history (状态流转历史)
  └── 1:N ── geometry_change_requests (几何变更申请)
                      └── 1:N ── engineer_confirmations (变更后重新确认)

powder_batches
  └── 1:N ── production_schedules (排产记录)
```

---

## 十一、接口一览（按业务模块）

| 模块 | 文件 | 核心接口 | 对状态的影响 |
|------|------|---------|-------------|
| 订单 | `orders.py` | `POST /orders/` | 创建 → pending |
| 订单 | `orders.py` | `POST /orders/{id}/transition` | 通用状态流转（校验 VALID_TRANSITIONS） |
| 工程师确认 | `confirmations.py` | `POST /orders/{id}/confirmation/` | 首次确认 → pending 不变 |
| 工程师确认 | `confirmations.py` | `PUT /orders/{id}/confirmation/reconfirm` | 重新确认 → change_pending → pending |
| 排产 | `schedules.py` | `POST /schedules/{order_id}` | pending/rework → scheduled |
| 排产 | `schedules.py` | `DELETE /schedules/{schedule_id}` | 删除最后排产 → scheduled → pending |
| 排产 | `schedules.py` | `POST /schedules/{id}/start-print` | scheduled → printing |
| 排产 | `schedules.py` | `POST /schedules/{id}/finish-print` | printing → inspecting |
| 质检 | `inspections.py` | `POST /inspections/{order_id}` | 通过 → assembly_ready；不通过 → rework |
| 几何变更 | `geometry_changes.py` | `POST /geometry-changes/{order_id}` | 非打印阶段 → change_pending；打印阶段 → 待评审 |
| 几何变更 | `geometry_changes.py` | `POST /geometry-changes/{id}/review` | 评审通过 → change_pending |
| 粉末批次 | `powder_batches.py` | `POST /powder-batches/{id}/mark-anomaly` | 标记异常+隔离，不影响订单状态 |
| 粉末批次 | `powder_batches.py` | `PUT /powder-batches/inspections/{id}/batch-review` | 完成复核，不影响订单状态 |
| 设备 | `equipment.py` | CRUD | 不影响订单状态 |
| 统计 | `analytics.py` | 4个GET接口 | 只读，不影响状态 |
