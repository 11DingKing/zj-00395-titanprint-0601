import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./titanprint.db")

VALID_TRANSITIONS = {
    "pending": ["scheduled", "change_pending"],
    "change_pending": ["pending", "scheduled"],
    "scheduled": ["printing", "pending", "change_pending"],
    "printing": ["inspecting", "change_pending"],
    "inspecting": ["rework", "assembly_ready"],
    "rework": ["scheduled", "inspecting", "change_pending"],
    "assembly_ready": [],
}

STATUS_LABELS = {
    "pending": "待确认",
    "change_pending": "变更待确认",
    "scheduled": "已排产",
    "printing": "打印中",
    "inspecting": "质检中",
    "rework": "返修",
    "assembly_ready": "可装配",
}

CHANGE_TYPE_LABELS = {
    "height": "身高变更",
    "inseam": "腿长变更",
    "riding_posture": "骑姿变更",
    "usage": "用途变更",
    "other": "其他变更",
}

CHANGE_REVIEW_STATUS_LABELS = {
    "pending": "待评审",
    "approved": "评审通过",
    "rejected": "评审驳回",
    "superseded": "已被替代",
}

DEFAULT_RECONFIRM_DELAY_HOURS = 24
PRINTING_CHANGE_REVIEW_REQUIRED = True
