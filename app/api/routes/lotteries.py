from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import (
    require_lotteries_read,
    require_lotteries_write,
)
from app.core.audit import log_mutation
from app.db.session import get_db
from app.schemas.lottery import LotteryCreate, LotteryResponse, LotteryUpdate
from app.services.lottery_service import LotteryService
from app.services.quota_service import QuotaExceededError, QuotaService
from app.services.quota_usage_service import QuotaUsageService

router = APIRouter(
    prefix="/api/v1/lotteries",
    tags=["Lotteries"],
)


@router.get("", response_model=list[LotteryResponse])
def list_lotteries(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_lotteries_read),
):
    return LotteryService.list_lotteries(db=db, tenant_id=tenant.tenant_id)


@router.get("/{lottery_id}", response_model=LotteryResponse)
def get_lottery(
    lottery_id: int,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_lotteries_read),
):
    return LotteryService.get_lottery(
        db=db,
        lottery_id=lottery_id,
        tenant_id=tenant.tenant_id,
    )


@router.post("", response_model=LotteryResponse, status_code=status.HTTP_201_CREATED)
def create_lottery(
    payload: LotteryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: TenantContext = Depends(require_lotteries_write),
):
    QuotaService.lock_tenant(db, tenant_id=tenant.tenant_id)
    current_usage = QuotaUsageService.get_current_usage(
        db,
        tenant_id=tenant.tenant_id,
        quota_code="lotteries.max",
    )
    try:
        QuotaService.enforce_if_configured(
            db,
            tenant_id=tenant.tenant_id,
            quota_code="lotteries.max",
            current_usage=current_usage,
            increment=1,
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Lottery quota exceeded",
        ) from exc

    lottery = LotteryService.create_lottery(
        db=db,
        payload=payload.model_dump(),
        tenant_id=tenant.tenant_id,
    )
    log_mutation(
        action="create",
        resource="lottery",
        resource_id=lottery.id,
        actor=current_user,
    )
    return lottery


@router.put("/{lottery_id}", response_model=LotteryResponse)
def update_lottery(
    lottery_id: int,
    payload: LotteryUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: TenantContext = Depends(require_lotteries_write),
):
    lottery = LotteryService.update_lottery(
        db=db,
        lottery_id=lottery_id,
        update_data=payload.model_dump(exclude_unset=True),
        tenant_id=tenant.tenant_id,
    )
    log_mutation(
        action="update",
        resource="lottery",
        resource_id=lottery.id,
        actor=current_user,
    )
    return lottery


@router.delete("/{lottery_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lottery(
    lottery_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: TenantContext = Depends(require_lotteries_write),
):
    LotteryService.delete_lottery(
        db=db,
        lottery_id=lottery_id,
        tenant_id=tenant.tenant_id,
    )
    log_mutation(
        action="delete",
        resource="lottery",
        resource_id=lottery_id,
        actor=current_user,
    )
