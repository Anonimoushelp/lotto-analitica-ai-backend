# isort: skip_file

from app.sources.four_digit_adapters import (
    AntioquenitaAdapter,
    CafeteritoAdapter,
    ChonticoAdapter,
    DoradoAdapter,
    FantasticaAdapter,
    PaisitaAdapter,
)
from app.sources.four_digit_parsers import (
    AntioquenitaJsonParser,
    CafeteritoJsonParser,
    ChonticoJsonParser,
    DoradoJsonParser,
    FantasticaJsonParser,
    PaisitaJsonParser,
)
from app.sources.parsers import HtmlTableParser
from app.sources.traditional_lottery_components import (
    CundinamarcaActaPdfParser,
    TraditionalLotteryAdapter,
    TraditionalLotteryHtmlParser,
)
from app.sources.provider_parser_adapter import (
    HtmlProviderParserAdapter,
    ProviderParserAdapter,
)
from app.sources.traditional_lottery import get_traditional_source


PROVIDER_COMPONENTS = {
    "ANTIOQUENITA": (AntioquenitaJsonParser, AntioquenitaAdapter),
    "CHONTICO": (ChonticoJsonParser, ChonticoAdapter),
    "DORADO": (DoradoJsonParser, DoradoAdapter),
    "CAFETERITO": (CafeteritoJsonParser, CafeteritoAdapter),
    "PAISITA": (PaisitaJsonParser, PaisitaAdapter),
    "FANTASTICA": (FantasticaJsonParser, FantasticaAdapter),
}

HTML_PROVIDER_COMPONENTS = {
    "ANTIOQUENITA": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={"ANTIOQUENITA_1", "ANTIOQUENITA_2"},
    ),
    "CHONTICO": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={
            "CHONTICO_DIA",
            "CHONTICO_NOCHE",
            "CHONTICO_SUPER_NOCHE",
        },
        draw_type_aliases={"SUPER_CHONTICO_NOCHE": "CHONTICO_SUPER_NOCHE"},
    ),
    "DORADO": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={"DORADO_DIA", "DORADO_TARDE", "DORADO_NOCHE"},
        draw_type_aliases={"DORADO_MANANA": "DORADO_DIA"},
        metadata_keys=("additional_value", "raw_additional_value"),
    ),
    "CAFETERITO": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={"CAFETERITO_TARDE", "CAFETERITO_NOCHE"},
    ),
    "PAISITA": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={"PAISITA_DIA", "PAISITA_NOCHE"},
        metadata_keys=("animal",),
    ),
    "FANTASTICA": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={"FANTASTICA_DIA", "FANTASTICA_NOCHE"},
        metadata_keys=("additional_value", "raw_additional_value"),
    ),
}


def build_provider_components(lottery_code: str):
    """Build the parser/adapter pair for a supported four-digit provider."""
    try:
        parser_type, adapter_type = PROVIDER_COMPONENTS[lottery_code.upper()]
    except KeyError as exc:
        raise KeyError(
            f"No four-digit provider components configured for {lottery_code}"
        ) from exc
    return ProviderParserAdapter(parser_type()), adapter_type()


def build_html_provider_parser(lottery_code: str) -> HtmlProviderParserAdapter:
    """Build the extraction parser for a supported HTML provider."""
    try:
        return HTML_PROVIDER_COMPONENTS[lottery_code.upper()]
    except KeyError as exc:
        raise KeyError(
            f"No HTML provider parser configured for {lottery_code}"
        ) from exc


TRADITIONAL_LOTTERY_CODES = {
    "LOTERIA_CUNDINAMARCA",
    "LOTERIA_TOLIMA",
    "LOTERIA_CRUZ_ROJA",
    "LOTERIA_HUILA",
    "LOTERIA_MANIZALES",
    "LOTERIA_VALLE",
    "LOTERIA_META",
    "LOTERIA_BOGOTA",
    "LOTERIA_QUINDIO",
    "LOTERIA_MEDELLIN",
    "LOTERIA_SANTANDER",
    "LOTERIA_RISARALDA",
    "LOTERIA_BOYACA",
    "LOTERIA_CAUCA",
}


TRADITIONAL_PARSER_FACTORIES = {
    "traditional_result_page": TraditionalLotteryHtmlParser,
    "traditional_result_page_embedded": TraditionalLotteryHtmlParser,
    "traditional_cundinamarca_acta_pdf": CundinamarcaActaPdfParser,
}

TRADITIONAL_ADAPTER_FACTORIES = {
    "traditional_four_digit_series": TraditionalLotteryAdapter,
}


def build_traditional_lottery_components(lottery_code: str):
    code = lottery_code.upper()
    if code not in TRADITIONAL_LOTTERY_CODES:
        raise KeyError(
            f"No traditional lottery components configured for {lottery_code}"
        )

    profile = get_traditional_source(code)
    try:
        parser_factory = TRADITIONAL_PARSER_FACTORIES[profile.parser_key]
    except KeyError as exc:
        raise KeyError(
            f"No traditional parser configured for {code}: {profile.parser_key}"
        ) from exc
    try:
        adapter_factory = TRADITIONAL_ADAPTER_FACTORIES[profile.adapter_key]
    except KeyError as exc:
        raise KeyError(
            f"No traditional adapter configured for {code}: {profile.adapter_key}"
        ) from exc

    return parser_factory(code), adapter_factory(code)
