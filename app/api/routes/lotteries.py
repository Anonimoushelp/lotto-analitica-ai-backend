from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.lottery import Lottery
from app.schemas.lottery import LotteryCreate, LotteryResponse, LotteryUpdate

router = APIRouter(
    prefix="/api/v1/lotteries",
    tags=["Lotteries"],
)


@router.get(
    "",
    response_model=list[LotteryResponse],
)
def list_lotteries(
    db: Session = Depends(get_db),
):
    statement = select(Lottery).order_by(Lottery.name)
    return db.scalars(statement).all()


@router.get(
    "/{lottery_id}",
    response_model=LotteryResponse,
)
def get_lottery(
    lottery_id: int,
    db: Session = Depends(get_db),
):
    lottery = db.get(Lottery, lottery_id)

    if lottery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lottery not found",
        )

    return lottery


@router.post(
    "",
    response_model=LotteryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lottery(
    payload: LotteryCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Lottery).where(Lottery.code == payload.code)
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lottery code already exists",
        )

    lottery = Lottery(**payload.model_dump())

    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    return lottery


@router.put(
    "/{lottery_id}",
    response_model=LotteryResponse,
)
def update_lottery(
    lottery_id: int,
    payload: LotteryUpdate,
    db: Session = Depends(get_db),
):
    lottery = db.get(Lottery, lottery_id)

    if lottery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lottery not found",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "code" in update_data:
        existing = db.scalar(
            select(Lottery).where(
                Lottery.code == update_data["code"],
                Lottery.id != lottery_id,
            )
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery code already exists",
            )

    for field, value in update_data.items():
        setattr(lottery, field, value)

    db.commit()
    db.refresh(lottery)

    return lottery


@router.delete(
    "/{lottery_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_lottery(
    lottery_id: int,
    db: Session = Depends(get_db),
):
    lottery = db.get(Lottery, lottery_id)

    if lottery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lottery not found",
        )

    db.delete(lottery)
    db.commit()
