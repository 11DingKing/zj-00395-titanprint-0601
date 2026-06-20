import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./titanprint.db")

VALID_TRANSITIONS = {
    "pending": ["scheduled"],
    "scheduled": ["printing"],
    "printing": ["inspecting"],
    "inspecting": ["rework", "assembly_ready"],
    "rework": ["inspecting"],
    "assembly_ready": [],
}

STATUS_LABELS = {
    "pending": "待确认",
    "scheduled": "已排产",
    "printing": "打印中",
    "inspecting": "质检中",
    "rework": "返修",
    "assembly_ready": "可装配",
}
