import re
from datetime import UTC, datetime
from urllib.parse import unquote

import httpx
import pytest

from app.scheduler.catalog_integration import (
    IntegrationStatus,
    build_catalog_scheduler_bindings,
)
from app.sources.fetchers import CundinamarcaActaSourceFetcher, SourceFetchResult
from app.sources.provider_registry import build_traditional_lottery_components


def _result(html: str) -> SourceFetchResult:
    return SourceFetchResult(
        url="https://example.test/resultados",
        content=html.encode(),
        fetched_at=datetime(2026, 9, 21, tzinfo=UTC),
        status_code=200,
        content_type="text/html; charset=utf-8",
    )


def test_traditional_parser_and_adapter_preserve_major_result_and_series():
    parser, adapter = build_traditional_lottery_components("LOTERIA_TOLIMA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Sorteo 4187 - lunes 14 de septiembre de 2026 "
                "Número 6845 Serie 051"
                "</body></html>"
            ),
            "LOTERIA_TOLIMA",
        )
    )
    normalized = adapter.normalize(records[0])
    assert normalized.draw_number == "4187"
    assert normalized.draw_date.isoformat() == "2026-09-14"
    assert normalized.main_numbers == [6845]
    assert normalized.metadata["series"] == "051"
    assert normalized.metadata["raw_result"] == "6845"


def test_all_catalog_ordinary_codes_have_component_mapping():
    bindings = build_catalog_scheduler_bindings()
    for binding in bindings:
        if binding.integration_status is not IntegrationStatus.EXTRAORDINARY_ONLY:
            parser, adapter = build_traditional_lottery_components(binding.lottery_code)
            assert parser is not None
            assert adapter.spec.lottery_code == binding.lottery_code


def test_traditional_adapter_rejects_non_four_digit_major_result():
    _, adapter = build_traditional_lottery_components("LOTERIA_TOLIMA")
    with pytest.raises(ValueError, match="exactly four digits"):
        adapter.normalize(
            {
                "draw_type": "LOTERIA_TOLIMA_ORDINARY",
                "draw_date": "2026-09-14",
                "draw_number": "4187",
                "main_numbers": [123],
                "metadata": {"raw_result": "123"},
            }
        )



def test_traditional_parser_accepts_abbreviated_month_and_numeric_date():
    parser, _ = build_traditional_lottery_components("LOTERIA_TOLIMA")
    abbreviated = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4188 - 21 de sept. de 2026 "
                "Número 4008 Serie 055</body></html>"
            ),
            "LOTERIA_TOLIMA",
        )
    )
    numeric = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4188 - 21/09/2026 "
                "Número 4008 Serie 055</body></html>"
            ),
            "LOTERIA_TOLIMA",
        )
    )
    assert abbreviated[0]["draw_date"] == "2026-09-21"
    assert numeric[0]["draw_date"] == "2026-09-21"
    assert abbreviated[0]["main_numbers"] == [4008]
    assert numeric[0]["main_numbers"] == [4008]


def test_traditional_parser_accepts_iso_date_and_colon_draw_label():
    parser, _ = build_traditional_lottery_components("LOTERIA_CAUCA")
    records = list(
        parser.parse(
            _result(
                "<html><body>Sorteo: 2629 Fecha: 2026-09-19 "
                "3 4 0 9 Serie 260</body></html>"
            ),
            "LOTERIA_CAUCA",
        )
    )
    assert records[0]["draw_number"] == "2629"
    assert records[0]["draw_date"] == "2026-09-19"
    assert records[0]["main_numbers"] == [3409]
    assert records[0]["metadata"]["series"] == "260"


def test_traditional_parser_accepts_month_first_real_format():
    parser, _ = build_traditional_lottery_components("LOTERIA_VALLE")
    records = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4867 Septiembre 23 2026 "
                "Número 4356 Serie 149</body></html>"
            ),
            "LOTERIA_VALLE",
        )
    )
    assert records[0]["draw_number"] == "4867"
    assert records[0]["draw_date"] == "2026-09-23"
    assert records[0]["main_numbers"] == [4356]
    assert records[0]["metadata"]["series"] == "149"


def test_traditional_parser_accepts_quindio_result_series_pair():
    parser, _ = build_traditional_lottery_components("LOTERIA_QUINDIO")
    records = list(
        parser.parse(
            _result(
                "<html><body>Resultado Sorteo 3016 del 2026-09-17 "
                "Premio Mayor 3853-160</body></html>"
            ),
            "LOTERIA_QUINDIO",
        )
    )
    assert records[0]["draw_number"] == "3016"
    assert records[0]["draw_date"] == "2026-09-17"
    assert records[0]["main_numbers"] == [3853]
    assert records[0]["metadata"]["series"] == "160"


def test_traditional_parser_accepts_month_first_date_with_comma():
    parser, _ = build_traditional_lottery_components("LOTERIA_BOYACA")
    records = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 4642 Septiembre 19, 2026 "
                "Número 8004 Serie 240</body></html>"
            ),
            "LOTERIA_BOYACA",
        )
    )
    assert records[0]["draw_number"] == "4642"
    assert records[0]["draw_date"] == "2026-09-19"
    assert records[0]["main_numbers"] == [8004]
    assert records[0]["metadata"]["series"] == "240"


def test_traditional_parser_decodes_html_entities_in_date():
    parser, _ = build_traditional_lottery_components("LOTERIA_RISARALDA")
    records = list(
        parser.parse(
            _result(
                "<html><body>Sorteo 2967 viernes 18 de septiembre "
                "de 2026 Número 6711 Serie 284</body></html>"
            ),
            "LOTERIA_RISARALDA",
        )
    )
    assert records[0]["draw_number"] == "2967"
    assert records[0]["draw_date"] == "2026-09-18"
    assert records[0]["main_numbers"] == [6711]
    assert records[0]["metadata"]["series"] == "284"


def test_traditional_parser_accepts_cruz_roja_homepage_format():
    parser, _ = build_traditional_lottery_components("LOTERIA_CRUZ_ROJA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "SORTEO 3171 DEL 15/09/2026 "
                "NÚMERO GANADOR PREMIO MAYOR "
                "0 0 1 6 SERIE 173"
                "</body></html>"
            )
        )
    )
    assert records[0]["draw_number"] == "3171"
    assert records[0]["draw_date"] == "2026-09-15"
    assert records[0]["main_numbers"] == [16]
    assert records[0]["metadata"]["raw_result"] == "0016"
    assert records[0]["metadata"]["series"] == "173"


def test_traditional_parser_preserves_spaced_series_from_boyaca_layout():
    parser, _ = build_traditional_lottery_components("LOTERIA_BOYACA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Resultado sorteo #4642 "
                "Sábado 19 de septiembre de 2026 "
                "Número Ganador 8 0 0 4 "
                "Serie 2 4 0"
                "</body></html>"
            )
        )
    )
    assert records[0]["draw_number"] == "4642"
    assert records[0]["draw_date"] == "2026-09-19"
    assert records[0]["main_numbers"] == [8004]
    assert records[0]["metadata"]["series"] == "240"



def test_cundinamarca_acta_parser_extracts_official_pdf_fields(monkeypatch):
    parser, adapter = build_traditional_lottery_components("LOTERIA_CUNDINAMARCA")

    class Page:
        def extract_text(self):
            return (
                "ACTA DE RESULTADOS SORTEO 4821 "
                "En Bogotá, D.C. a los 21 del mes de Septiembre de 2026 "
                "PREMIO MAYOR 6000 MILLONES 6000 MILLONES 5341 078 BOGOTA"
            )

    class Reader:
        def __init__(self):
            self.pages = [Page()]

    monkeypatch.setattr(
        "app.sources.traditional_lottery_components.PdfReader",
        lambda _stream: Reader(),
    )
    result = SourceFetchResult(
        url=(
            "https://www.loteriadecundinamarca.com.co/"
            "public/files/actas/2026/Acta%20Sorteo%204821.pdf"
        ),
        content=b"%PDF-1.7",
        fetched_at=datetime(2026, 9, 25, tzinfo=UTC),
        status_code=200,
        content_type="application/pdf",
    )

    records = list(parser.parse(result, "LOTERIA_CUNDINAMARCA"))
    normalized = adapter.normalize(records[0])

    assert normalized.draw_number == "4821"
    assert normalized.draw_date.isoformat() == "2026-09-21"
    assert normalized.main_numbers == [5341]
    assert normalized.metadata["series"] == "078"




def test_cundinamarca_acta_fetcher_accepts_result_pdf_links_without_fixed_path():
    page_url = "https://www.loteriadecundinamarca.com.co/?p=actas-de-resultados"
    page = """
    <html><body>
      <a href="/public/files/documentos/2026/acta-resultados-sorteo-4820.pdf">4820</a>
      <a href="/public/files/actas/2026/Acta%20Sorteo%204821.pdf">4821</a>
    </body></html>
    """

    def handler(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                text=page,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(
            200,
            content=b"%PDF-1.7 fake",
            headers={"content-type": "application/pdf"},
        )

    fetcher = CundinamarcaActaSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    result = fetcher.fetch(page_url)

    assert "4821" in result.url
    assert "application/pdf" in result.content_type

def test_cundinamarca_acta_fetcher_selects_latest_official_acta():
    page_url = "https://www.loteriadecundinamarca.com.co/?p=actas-de-resultados"
    page = """
    <html><body>
      <a href="public/files/actas/2026/Acta%20Sorteo%204820.pdf">4820</a>
      <a href="public/files/actas/2026/Acta%20Sorteo%204821.pdf">4821</a>
    </body></html>
    """

    def handler(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                text=page,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(
            200,
            content=b"%PDF-1.7 fake",
            headers={"content-type": "application/pdf"},
        )

    fetcher = CundinamarcaActaSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    result = fetcher.fetch(page_url)

    assert "4821" in result.url
    assert "application/pdf" in result.content_type



def test_boyaca_real_layout_prefers_labeled_winner_over_secondary_numbers():
    parser, _ = build_traditional_lottery_components("LOTERIA_BOYACA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Resultado sorteo #4642 "
                "Sábado 19 de septiembre de 2026 "
                "Número Ganador 8 0 0 4 "
                "Serie 2 4 0 "
                "Resultados secos 7735 186"
                "</body></html>"
            )
        )
    )
    assert records[0]["draw_number"] == "4642"
    assert records[0]["draw_date"] == "2026-09-19"
    assert records[0]["main_numbers"] == [8004]
    assert records[0]["metadata"]["series"] == "240"


def test_risaralda_parser_accepts_official_sorteo_n_label():
    parser, _ = build_traditional_lottery_components("LOTERIA_RISARALDA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Sorteo N° 2968 "
                "viernes 25 de septiembre de 2026 "
                "Premio mayor 6 7 1 2 Serie 285"
                "</body></html>"
            )
        )
    )
    assert records[0]["draw_number"] == "2968"
    assert records[0]["draw_date"] == "2026-09-25"
    assert records[0]["main_numbers"] == [6712]


def test_risaralda_parser_accepts_sorteo_no_label():
    parser, _ = build_traditional_lottery_components("LOTERIA_RISARALDA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Sorteo No. 2968 "
                "Premio mayor 6 7 1 2 Serie 285"
                "</body></html>"
            )
        )
    )
    assert records[0]["draw_number"] == "2968"
    assert records[0]["draw_date"] == "2026-09-25"
    assert records[0]["main_numbers"] == [6712]


def test_risaralda_date_allows_comma_after_day_and_month():
    parser, _ = build_traditional_lottery_components("LOTERIA_RISARALDA")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Sorteo 2967 viernes, 18, de septiembre, 2026 "
                "Premio mayor 6 7 1 1 Serie 284"
                "</body></html>"
            )
        )
    )
    assert records[0]["draw_number"] == "2967"
    assert records[0]["draw_date"] == "2026-09-18"
    assert records[0]["main_numbers"] == [6711]


def test_cundinamarca_acta_fetcher_discovers_newer_contiguous_acta():
    page_url = "https://www.loteriadecundinamarca.com.co/?p=actas-de-resultados"
    indexed_url = (
        "https://www.loteriadecundinamarca.com.co/public/files/actas/2026/"
        "Acta%20Sorteo%204800.pdf"
    )

    def handler(request):
        match = re.search(r"Sorteo[ %20]+(\d+)\.pdf$", unquote(request.url.path))
        assert match is not None
        draw = int(match.group(1))
        if draw <= 4821:
            return httpx.Response(
                200,
                content=b"%PDF-1.7 fake",
                headers={"content-type": "application/pdf"},
            )
        return httpx.Response(404)

    fetcher = CundinamarcaActaSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    discovered = fetcher._discover_newer_acta(
        index_url=page_url,
        indexed_url=indexed_url,
        latest_draw=4800,
    )

    assert discovered is not None
    assert "Sorteo%204821.pdf" in discovered


def test_persist_idempotency_allows_missing_optional_core_fields():
    from app.models.lottery_draw import LotteryDraw
    from app.services.lottery_draw_service import LotteryDrawService
    from app.sources.contracts import RawDrawRecord

    existing = LotteryDraw(
        draw_type="LOTERIA_TOLIMA_ORDINARY",
        draw_number="4188",
        draw_date=datetime(2026, 9, 21, tzinfo=UTC).date(),
        draw_time=None,
        main_numbers=[4008],
        bonus_numbers=[55],
    )
    record = RawDrawRecord(
        lottery_code="LOTERIA_TOLIMA",
        draw_type="LOTERIA_TOLIMA_ORDINARY",
        draw_number="4188",
        draw_date=datetime(2026, 9, 21, tzinfo=UTC).date(),
        draw_time=None,
        main_numbers=[4008],
        bonus_numbers=None,
        source_name="LOTERIA_TOLIMA",
        source_url="https://example.test",
        source_timestamp=datetime(2026, 9, 25, tzinfo=UTC),
        metadata={"raw_result": "4008", "digit_count": 4},
    )
    assert LotteryDrawService._core_payload_compatible(existing, record)


def test_traditional_parser_accepts_textual_month_with_slash_separators():
    parser, _ = build_traditional_lottery_components("LOTERIA_MEDELLIN")
    records = list(
        parser.parse(
            _result(
                "<html><body>"
                "Sorteo número 4853 del 18/Septiembre/2026 "
                "Número 8535 Serie 183"
                "</body></html>"
            ),
            "LOTERIA_MEDELLIN",
        )
    )
    assert records[0]["draw_number"] == "4853"
    assert records[0]["draw_date"] == "2026-09-18"
    assert records[0]["main_numbers"] == [8535]
    assert records[0]["metadata"]["series"] == "183"


def test_cundinamarca_acta_fetcher_falls_back_when_index_is_dynamic():
    page_url = "https://www.loteriadecundinamarca.com.co/?p=actas-de-resultados"
    page = "<html><body><div>Actas cargadas dinámicamente</div></body></html>"

    def handler(request):
        if "actas-de-resultados" in str(request.url):
            return httpx.Response(
                200,
                text=page,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        match = re.search(r"Sorteo\s+(\d+)\.pdf$", unquote(request.url.path))
        assert match is not None
        draw = int(match.group(1))
        if draw == 4821:
            return httpx.Response(
                200,
                content=b"%PDF-1.7 fake",
                headers={"content-type": "application/pdf"},
            )
        return httpx.Response(404)

    fetcher = CundinamarcaActaSourceFetcher(
        transport=httpx.MockTransport(handler)
    )
    result = fetcher.fetch(page_url)

    assert "Sorteo%204821.pdf" in result.url
    assert "application/pdf" in result.content_type
