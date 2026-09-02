from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.data_warehouse import (
    DataMartResponse,
    OlapCubeResponse,
    OlapQueryRequest,
    OlapQueryResponse,
    WarehouseKPIResponse,
)
from app.services.data_warehouse_service import DataWarehouseService

router = APIRouter(
    prefix="/api/v1/data-warehouse",
    tags=["Data Warehouse & OLAP"],
)


@router.get("/kpis", response_model=WarehouseKPIResponse)
def get_kpis(db: Session = Depends(get_db)):
    return DataWarehouseService.kpis(db)


@router.get("/marts", response_model=list[DataMartResponse])
def get_marts(db: Session = Depends(get_db)):
    return DataWarehouseService.marts(db)


@router.get("/cubes", response_model=list[OlapCubeResponse])
def get_cubes():
    return DataWarehouseService.cubes()


@router.post("/query", response_model=OlapQueryResponse)
def execute_query(
    payload: OlapQueryRequest,
    db: Session = Depends(get_db),
):
    return DataWarehouseService.query(db, payload)
