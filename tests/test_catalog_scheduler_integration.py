from __future__ import annotations

from app.catalog.colombia_lotteries_2026 import (
    COLOMBIA_LOTTERIES_2026,
    LotteryStatus,
)
from app.scheduler.catalog_integration import (
    CALENDAR_AUTHORITY_URL,
    IntegrationStatus,
    build_catalog_scheduler_bindings,
    validate_catalog_scheduler_bindings,
)


def test_catalog_scheduler_binding_covers_all_catalog_entries():
    bindings = build_catalog_scheduler_bindings()
    assert len(bindings) == len(COLOMBIA_LOTTERIES_2026)
    assert validate_catalog_scheduler_bindings(bindings) == []


def test_binding_preserves_official_calendar_authority_and_chain():
    bindings = build_catalog_scheduler_bindings()
    assert CALENDAR_AUTHORITY_URL.startswith("https://cnjsa.coljuegos.gov.co/")
    for binding in bindings:
        assert binding.source.validator_key == "lottery_draw_validator"
        assert binding.source.ingestion_mode == (
            "fetch_parse_normalize_validate_persist"
        )


def test_suspended_quindio_does_not_become_schedulable():
    binding = next(
        item
        for item in build_catalog_scheduler_bindings()
        if item.lottery_code == "LOTERIA_QUINDIO"
    )
    assert binding.integration_status is IntegrationStatus.SUSPENDED
    assert binding.calendar_rule is not None
    assert binding.calendar_rule.enabled is False


def test_extra_colombia_has_no_ordinary_scheduler_rule():
    binding = next(
        item
        for item in build_catalog_scheduler_bindings()
        if item.lottery_code == "EXTRA_COLOMBIA"
    )
    assert binding.integration_status is IntegrationStatus.EXTRAORDINARY_ONLY
    assert binding.calendar_rule is None
    assert binding.draw_type == "EXTRA_COLOMBIA_EXTRAORDINARY"


def test_unverified_sources_are_not_marked_ready():
    bindings = build_catalog_scheduler_bindings()
    for binding in bindings:
        if binding.lottery_code != "EXTRA_COLOMBIA":
            lottery = next(
                item
                for item in COLOMBIA_LOTTERIES_2026
                if item.code == binding.lottery_code
            )
            if lottery.status is LotteryStatus.ACTIVE and not lottery.primary_source_verified:
                assert binding.integration_status is IntegrationStatus.PENDING_SOURCE
