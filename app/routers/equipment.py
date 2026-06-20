from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PrintEquipment
from app.schemas import PrintEquipmentCreate, PrintEquipmentOut

router = APIRouter(prefix="/equipment", tags=["print-equipment"])


@router.post("/", response_model=PrintEquipmentOut, status_code=201)
def create_equipment(payload: PrintEquipmentCreate, db: Session = Depends(get_db)):
    existing = db.query(PrintEquipment).filter(PrintEquipment.name == payload.name).first()
    if existing:
        raise HTTPException(400, "设备名称已存在")
    equipment = PrintEquipment(**payload.model_dump())
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


@router.get("/", response_model=list[PrintEquipmentOut])
def list_equipment(db: Session = Depends(get_db)):
    return db.query(PrintEquipment).all()


@router.get("/{equipment_id}", response_model=PrintEquipmentOut)
def get_equipment(equipment_id: int, db: Session = Depends(get_db)):
    eq = db.query(PrintEquipment).filter(PrintEquipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(404, "设备不存在")
    return eq


@router.patch("/{equipment_id}", response_model=PrintEquipmentOut)
def update_equipment(equipment_id: int, payload: PrintEquipmentCreate, db: Session = Depends(get_db)):
    eq = db.query(PrintEquipment).filter(PrintEquipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(404, "设备不存在")
    for k, v in payload.model_dump().items():
        setattr(eq, k, v)
    db.commit()
    db.refresh(eq)
    return eq
