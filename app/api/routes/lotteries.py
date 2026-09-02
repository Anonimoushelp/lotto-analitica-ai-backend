from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.db.session import get_db
from app.schemas.lottery import LotteryCreate, LotteryResponse, LotteryUpdate
from app.services.lottery_service import LotteryService

router = APIRouter(
    prefix="/api/v1/lotteries",
    tags=["Lotteries"],
)


@router.get("", response_model=list[LotteryResponse])
def list_lotteries(db: Session = Depends(get_db)):
    return LotteryService.list_lotteries(db=db)


@router.get("/{lottery_id}", response_model=LotteryResponse)
def get_lottery(lottery_id: int, db: Session = Depends(get_db)):
    return LotteryService.get_lottery(db=db, lottery_id=lottery_id)


@router.post("", response_model=LotteryResponse, status_code=status.HTTP_201_CREATED)
def create_lottery(
    payload: LotteryCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    return LotteryService.create_lottery(
        db=db,
        payload=payload.model_dump(),
    )


@router.put("/{lottery_id}", response_model=LotteryResponse)
def update_lottery(
    lottery_id: int,
    payload: LotteryUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    return LotteryService.update_lottery(
        db=db,
        lottery_id=lottery_id,
        update_data=payload.model_dump(exclude_unset=True),
    )


@router.delete("/{lottery_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lottery(
    lottery_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    LotteryService.delete_lottery(db=db, lottery_id=lottery_id)
