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
from app.sources.provider_parser_adapter import (
    HtmlProviderParserAdapter,
    ProviderParserAdapter,
)


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
    ),
    "DORADO": HtmlProviderParserAdapter(
        parser=HtmlTableParser(),
        allowed_draw_types={"DORADO_DIA", "DORADO_TARDE", "DORADO_NOCHE"},
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
