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
from app.sources.provider_parser_adapter import ProviderParserAdapter


PROVIDER_COMPONENTS = {
    "ANTIOQUENITA": (AntioquenitaJsonParser, AntioquenitaAdapter),
    "CHONTICO": (ChonticoJsonParser, ChonticoAdapter),
    "DORADO": (DoradoJsonParser, DoradoAdapter),
    "CAFETERITO": (CafeteritoJsonParser, CafeteritoAdapter),
    "PAISITA": (PaisitaJsonParser, PaisitaAdapter),
    "FANTASTICA": (FantasticaJsonParser, FantasticaAdapter),
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
