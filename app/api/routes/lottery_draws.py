from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.tenant import TenantContext
from app.api.dependencies.tenant_auth import (
    require_draws_read,
    require_draws_write,
)
from app.core.audit import log_mutation
from app.db.session import get_db
from app.schemas.lottery_draw import (
    LotteryDrawCreate,
    LotteryDrawResponse,
    LotteryDrawUpdate,
)
from app.services.lottery_draw_service import LotteryDrawService
from app.services.quota_service import QuotaExceededError, QuotaService
from app.services.quota_usage_service import QuotaUsageService

DEFAULT_DRAW_LIST_LIMIT = 100
MAX_DRAW_LIST_LIMIT = 500

router = APIRouter(
    prefix="/api/v1/draws",
    tags=["Lottery Draws"],
)


@router.get("", response_model=list[LotteryDrawResponse])
def list_draws(
    lottery_id: int | None = Query(default=None, gt=0),
    limit: int = Query(
        default=DEFAULT_DRAW_LIST_LIMIT,
        ge=1,
        le=MAX_DRAW_LIST_LIMIT,
    ),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_draws_read),
):
    return LotteryDrawService.list_draws(
        db=db,
        tenant_id=tenant.tenant_id,
        lottery_id=lottery_id,
        limit=limit,
    )


@router.get("/{draw_id}", response_model=LotteryDrawResponse)
def get_draw(
    draw_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_draws_read),
):
    return LotteryDrawService.get_draw(
        db=db,
        draw_id=draw_id,
        tenant_id=tenant.tenant_id,
    )


@router.post("", response_model=LotteryDrawResponse, status_code=status.HTTP_201_CREATED)
def create_draw(
    payload: LotteryDrawCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: TenantContext = Depends(require_draws_write),
):
    current_usage = QuotaUsageService.get_current_usage(
        db,
        tenant_id=tenant.tenant_id,
        quota_code="draws.max",
    )
    try:
        QuotaService.enforce_if_configured(
            db,
            tenant_id=tenant.tenant_id,
            quota_code="draws.max",
            current_usage=current_usage,
            increment=1,
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Draw quota exceeded",
        ) from exc

    draw = LotteryDrawService.create_draw(
        db=db,
        tenant_id=tenant.tenant_id,
        lottery_id=payload.lottery_id,
        draw_number=payload.draw_number,
        draw_date=payload.draw_date,
        main_numbers=payload.main_numbers,
        bonus_numbers=payload.bonus_numbers,
        source=payload.source,
        metadata_json=payload.metadata_json,
    )
    log_mutation(
        action="create",
        resource="draw",
        resource_id=draw.id,
        actor=current_user,
    )
    return draw


@router.put("/{draw_id}", response_model=LotteryDrawResponse)
def update_draw(
    payload: LotteryDrawUpdate,
    draw_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: TenantContext = Depends(require_draws_write),
):
    update_data = payload.model_dump(exclude_unset=True)
    draw = LotteryDrawService.update_draw(
        db=db,
        draw_id=draw_id,
        tenant_id=tenant.tenant_id,
        update_data=update_data,
    )
    log_mutation(
        action="update",
        resource="draw",
        resource_id=draw.id,
        actor=current_user,
    )
    return draw


@router.delete("/{draw_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draw(
    draw_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: TenantContext = Depends(require_draws_write),
):
    LotteryDrawService.delete_draw(
        db=db,
        draw_id=draw_id,
        tenant_id=tenant.tenant_id,
    )
    log_mutation(
        action="delete",
        resource="draw",
        resource_id=draw_id,
        actor=current_user,
    )
