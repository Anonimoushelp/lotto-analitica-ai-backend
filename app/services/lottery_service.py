from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.repositories.lottery_repository import LotteryRepository


class LotteryService:
    @staticmethod
    def list_lotteries(db: Session, tenant_id: int) -> list[Lottery]:
        return LotteryRepository.list(db=db, tenant_id=tenant_id)

    @staticmethod
    def get_lottery(db: Session, lottery_id: int, tenant_id: int) -> Lottery:
        lottery = LotteryRepository.get_by_id(
            db=db,
            lottery_id=lottery_id,
            tenant_id=tenant_id,
        )
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
        tenant_id: int,
    ) -> Lottery:
        if LotteryRepository.get_by_code(
            db=db,
            code=payload["code"],
            tenant_id=tenant_id,
        ) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery code already exists",
            )

        lottery = Lottery(**payload, tenant_id=tenant_id)
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
        tenant_id: int,
    ) -> Lottery:
        lottery = LotteryService.get_lottery(
            db=db,
            lottery_id=lottery_id,
            tenant_id=tenant_id,
        )

        if "code" in update_data:
            existing = LotteryRepository.get_by_code(
                db=db,
                code=update_data["code"],
                tenant_id=tenant_id,
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
    def delete_lottery(db: Session, lottery_id: int, tenant_id: int) -> None:
        lottery = LotteryService.get_lottery(
            db=db,
            lottery_id=lottery_id,
            tenant_id=tenant_id,
        )
        LotteryRepository.delete(db=db, lottery=lottery)
