from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.repositories.lottery_repository import LotteryRepository


class LotteryService:
    @staticmethod
    def list_lotteries(db: Session) -> list[Lottery]:
        return LotteryRepository.list(db=db)

    @staticmethod
    def get_lottery(db: Session, lottery_id: int) -> Lottery:
        lottery = LotteryRepository.get_by_id(db=db, lottery_id=lottery_id)
        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )
        return lottery

    @staticmethod
    def create_lottery(
        db: Session,
        payload: dict,
    ) -> Lottery:
        if LotteryRepository.get_by_code(db=db, code=payload["code"]) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery code already exists",
            )

        lottery = Lottery(**payload)
        try:
            return LotteryRepository.create(db=db, lottery=lottery)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery code already exists",
            ) from exc

    @staticmethod
    def update_lottery(
        db: Session,
        lottery_id: int,
        update_data: dict,
    ) -> Lottery:
        lottery = LotteryService.get_lottery(db=db, lottery_id=lottery_id)

        if "code" in update_data:
            existing = LotteryRepository.get_by_code(
                db=db,
                code=update_data["code"],
            )
            if existing is not None and existing.id != lottery_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Lottery code already exists",
                )

        for field, value in update_data.items():
            setattr(lottery, field, value)

        try:
            return LotteryRepository.update(db=db, lottery=lottery)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery code already exists",
            ) from exc

    @staticmethod
    def delete_lottery(db: Session, lottery_id: int) -> None:
        lottery = LotteryService.get_lottery(db=db, lottery_id=lottery_id)
        LotteryRepository.delete(db=db, lottery=lottery)
