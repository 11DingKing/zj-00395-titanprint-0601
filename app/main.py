from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import engine, Base
from app.routers import orders, confirmations, schedules, inspections, analytics, equipment


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="TitanPrint API",
    description="全3D打印钛合金车架定制流程管理后端",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(orders.router)
app.include_router(confirmations.router)
app.include_router(schedules.router)
app.include_router(inspections.router)
app.include_router(analytics.router)
app.include_router(equipment.router)


@app.get("/")
def root():
    return {"service": "TitanPrint API", "version": "1.0.0"}
