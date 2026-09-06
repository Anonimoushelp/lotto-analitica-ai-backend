from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin, require_admin_or_analyst
from app.api.dependencies.tenant import TenantContext, get_tenant_context
from app.core.audit import log_mutation
from app.db.session import get_db
from app.schemas.lottery import LotteryCreate, LotteryResponse, LotteryUpdate
from app.services.lottery_service import LotteryService

router = APIRouter(
    prefix="/api/v1/lotteries",
    tags=["Lotteries"],
)


@router.get("", response_model=list[LotteryResponse])
def list_lotteries(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_analyst),
    tenant: TenantContext = Depends(get_tenant_context),
):
    return LotteryService.list_lotteries(db=db, tenant_id=tenant.tenant_id)


@router.get("/{lottery_id}", response_model=LotteryResponse)
def get_lottery(
    lottery_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_analyst),
    tenant: TenantContext = Depends(get_tenant_context),
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
    current_user=Depends(require_admin),
    tenant: TenantContext = Depends(get_tenant_context),
):
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
    current_user=Depends(require_admin),
    tenant: TenantContext = Depends(get_tenant_context),
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
    current_user=Depends(require_admin),
    tenant: TenantContext = Depends(get_tenant_context),
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
