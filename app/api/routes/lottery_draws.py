from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin_or_analyst
from app.db.session import get_db
from app.schemas.lottery_draw import (
    LotteryDrawCreate,
    LotteryDrawResponse,
    LotteryDrawUpdate,
)
from app.services.lottery_draw_service import LotteryDrawService

router = APIRouter(
    prefix="/api/v1/draws",
    tags=["Lottery Draws"],
)


@router.get("", response_model=list[LotteryDrawResponse])
def list_draws(lottery_id: int | None = None, db: Session = Depends(get_db)):
    return LotteryDrawService.list_draws(db=db, lottery_id=lottery_id)


@router.get("/{draw_id}", response_model=LotteryDrawResponse)
def get_draw(draw_id: int, db: Session = Depends(get_db)):
    return LotteryDrawService.get_draw(db=db, draw_id=draw_id)


@router.post("", response_model=LotteryDrawResponse, status_code=status.HTTP_201_CREATED)
def create_draw(
    payload: LotteryDrawCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_analyst),
):
    return LotteryDrawService.create_draw(
        db=db,
        lottery_id=payload.lottery_id,
        draw_number=payload.draw_number,
        draw_date=payload.draw_date,
        main_numbers=payload.main_numbers,
        bonus_numbers=payload.bonus_numbers,
        source=payload.source,
        metadata_json=payload.metadata_json,
    )


@router.put("/{draw_id}", response_model=LotteryDrawResponse)
def update_draw(
    draw_id: int,
    payload: LotteryDrawUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_analyst),
):
    update_data = payload.model_dump(exclude_unset=True)
    return LotteryDrawService.update_draw(
        db=db,
        draw_id=draw_id,
        update_data=update_data,
    )


@router.delete("/{draw_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draw(
    draw_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin_or_analyst),
):
    LotteryDrawService.delete_draw(db=db, draw_id=draw_id)
