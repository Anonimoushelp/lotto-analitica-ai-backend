from app.sources.catalog import build_ingestion_catalog
from app.sources.traditional_lottery import get_traditional_source


def test_manizales_enabled_and_santander_remains_disabled_until_dynamic_endpoint_is_verified():
    catalog = {job.key: job for job in build_ingestion_catalog()}

    assert get_traditional_source("LOTERIA_MANIZALES").verified is True
    assert get_traditional_source("LOTERIA_SANTANDER").verified is False
    assert catalog["loteria_manizales-traditional-html"].enabled is True
    assert catalog["loteria_santander-traditional-html"].enabled is False


def test_suspended_or_extraordinary_traditional_sources_are_disabled_in_ingestion_catalog():
    catalog = {job.lottery_code: job for job in build_ingestion_catalog()}

    assert catalog["LOTERIA_QUINDIO"].enabled is False
    assert catalog["EXTRA_COLOMBIA"].enabled is False
