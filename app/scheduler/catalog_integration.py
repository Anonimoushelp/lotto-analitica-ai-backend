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


# The CNJSA 2026 calendar is authoritative for ordinary lottery dates.
# Operator result URLs and provider-specific parsers are deliberately separate:
# a calendar entry must never imply that a source has been verified.
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
                    lottery_code=lottery.code,
                    draw_type=f"{lottery.code}_EXTRAORDINARY",
                    calendar_rule=None,
                    source=_operator_source(lottery),
                    integration_status=IntegrationStatus.EXTRAORDINARY_ONLY,
                )
            )
            continue

        draw_type = f"{lottery.code}_ORDINARY"
        calendar_rule = (
            ScheduledDraw(
                lottery_code=lottery.code,
                draw_type=draw_type,
                expected_time=None,  # type: ignore[arg-type]
                weekdays=frozenset({lottery.ordinary_weekday})
                if lottery.ordinary_weekday is not None
                else frozenset(),
                tolerance_minutes=90,
                enabled=lottery.status is LotteryStatus.ACTIVE,
            )
            if lottery.ordinary_weekday is not None
            else None
        )

        status = (
            IntegrationStatus.SUSPENDED
            if lottery.status is LotteryStatus.SUSPENDED_ORDINARY
            else (
                IntegrationStatus.READY_FOR_CONTROLLED_TEST
                if lottery.primary_source_verified
                else IntegrationStatus.PENDING_SOURCE
            )
        )
        bindings.append(
            CatalogDrawBinding(
                lottery_code=lottery.code,
                draw_type=draw_type,
                calendar_rule=calendar_rule,
                source=_operator_source(lottery),
                integration_status=status,
            )
        )

    return tuple(bindings)


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
                errors.append(f"{binding.lottery_code}: extraordinary entry has calendar")
            continue

        if binding.calendar_rule is None:
            errors.append(f"{binding.lottery_code}: missing ordinary calendar rule")
        elif (
            lottery.ordinary_weekday is not None
            and binding.calendar_rule.weekdays != frozenset({lottery.ordinary_weekday})
        ):
            errors.append(f"{binding.lottery_code}: calendar weekday mismatch")

        if (
            lottery.status is LotteryStatus.SUSPENDED_ORDINARY
            and binding.integration_status is not IntegrationStatus.SUSPENDED
        ):
            errors.append(f"{binding.lottery_code}: suspension not propagated")

    return errors
