from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from app.catalog.colombia_lotteries_2026 import (
    COLOMBIA_LOTTERIES_2026,
    ColombiaLottery2026,
    LotteryStatus,
)
from app.scheduler.draw_schedule import ScheduledDraw
from app.sources.traditional_lottery import get_traditional_source


class IntegrationStatus(StrEnum):
    READY_FOR_CONTROLLED_TEST = "READY_FOR_CONTROLLED_TEST"
    PENDING_SOURCE = "PENDING_SOURCE"
    SUSPENDED = "SUSPENDED"
    EXTRAORDINARY_ONLY = "EXTRAORDINARY_ONLY"


@dataclass(frozen=True)
class SourceBinding:
    primary_name: str
    primary_url: str | None
    parser_key: str | None
    adapter_key: str | None
    validator_key: str
    ingestion_mode: str
    verified: bool = False


@dataclass(frozen=True)
class CatalogDrawBinding:
    lottery_code: str
    draw_type: str
    calendar_rule: ScheduledDraw | None
    source: SourceBinding
    integration_status: IntegrationStatus


CALENDAR_AUTHORITY_URL = (
    "https://cnjsa.coljuegos.gov.co/publicaciones/306418/"
    "cronograma-de-sorteos-ordinarios-y-extraordinarios/"
)


def _operator_source(lottery: ColombiaLottery2026) -> SourceBinding:
    profile = get_traditional_source(lottery.code)
    return SourceBinding(
        primary_name=profile.name,
        primary_url=profile.result_url,
        parser_key=profile.parser_key,
        adapter_key=profile.adapter_key,
        validator_key="lottery_draw_validator",
        ingestion_mode="fetch_parse_normalize_validate_persist",
        verified=profile.verified and lottery.primary_source_verified,
    )


def build_catalog_scheduler_bindings() -> tuple[CatalogDrawBinding, ...]:
    bindings: list[CatalogDrawBinding] = []
    for lottery in COLOMBIA_LOTTERIES_2026:
        if lottery.status is LotteryStatus.EXTRAORDINARY_ONLY:
            bindings.append(
                CatalogDrawBinding(
                    lottery.code,
                    f"{lottery.code}_EXTRAORDINARY",
                    None,
                    _operator_source(lottery),
                    IntegrationStatus.EXTRAORDINARY_ONLY,
                )
            )
            continue

        draw_type = f"{lottery.code}_ORDINARY"
        calendar_rule = (
            ScheduledDraw(
                lottery_code=lottery.code,
                draw_type=draw_type,
                expected_time=None,
                weekdays=(
                    frozenset({lottery.ordinary_weekday})
                    if lottery.ordinary_weekday is not None
                    else frozenset()
                ),
                enabled=lottery.status is LotteryStatus.ACTIVE,
                calendar_only=True,
            )
            if lottery.ordinary_weekday is not None
            else None
        )
        source = _operator_source(lottery)
        status = (
            IntegrationStatus.SUSPENDED
            if lottery.status is LotteryStatus.SUSPENDED_ORDINARY
            else (
                IntegrationStatus.READY_FOR_CONTROLLED_TEST
                if source.verified
                else IntegrationStatus.PENDING_SOURCE
            )
        )
        bindings.append(
            CatalogDrawBinding(
                lottery.code,
                draw_type,
                calendar_rule,
                source,
                status,
            )
        )
    return tuple(bindings)


def ready_catalog_schedules(
    bindings: tuple[CatalogDrawBinding, ...] | None = None,
) -> tuple[ScheduledDraw, ...]:
    bindings = bindings or build_catalog_scheduler_bindings()
    return tuple(
        binding.calendar_rule
        for binding in bindings
        if binding.integration_status is IntegrationStatus.READY_FOR_CONTROLLED_TEST
        and binding.calendar_rule is not None
    )


def validate_catalog_scheduler_bindings(
    bindings: tuple[CatalogDrawBinding, ...],
) -> list[str]:
    errors: list[str] = []
    expected_codes = {lottery.code for lottery in COLOMBIA_LOTTERIES_2026}
    actual_codes = {binding.lottery_code for binding in bindings}
    if actual_codes != expected_codes:
        errors.append("Catalog and scheduler binding codes do not match")

    for binding in bindings:
        if not binding.draw_type:
            errors.append(f"{binding.lottery_code}: missing draw_type")
        if not binding.source.validator_key:
            errors.append(f"{binding.lottery_code}: missing validator")
        if binding.source.primary_url is not None:
            parsed = urlparse(binding.source.primary_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{binding.lottery_code}: invalid primary_url")

        lottery = next(
            item for item in COLOMBIA_LOTTERIES_2026
            if item.code == binding.lottery_code
        )
        if lottery.status is LotteryStatus.EXTRAORDINARY_ONLY:
            if binding.calendar_rule is not None:
                errors.append(
                    f"{binding.lottery_code}: extraordinary entry has calendar"
                )
            continue
        if binding.calendar_rule is None:
            errors.append(f"{binding.lottery_code}: missing ordinary calendar rule")
        elif (
            lottery.ordinary_weekday is not None
            and binding.calendar_rule.weekdays
            != frozenset({lottery.ordinary_weekday})
        ):
            errors.append(f"{binding.lottery_code}: calendar weekday mismatch")
        if (
            binding.calendar_rule is not None
            and lottery.status is LotteryStatus.ACTIVE
            and not binding.calendar_rule.calendar_only
        ):
            errors.append(f"{binding.lottery_code}: active catalog rule is not calendar-only")
        if (
            lottery.status is LotteryStatus.SUSPENDED_ORDINARY
            and binding.integration_status is not IntegrationStatus.SUSPENDED
        ):
            errors.append(f"{binding.lottery_code}: suspension not propagated")
        if (
            binding.integration_status is IntegrationStatus.READY_FOR_CONTROLLED_TEST
            and not binding.source.verified
        ):
            errors.append(f"{binding.lottery_code}: ready binding has unverified source")
    return errors
