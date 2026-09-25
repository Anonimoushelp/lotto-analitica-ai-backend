from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TraditionalLotterySource:
    name: str
    result_url: str | None
    parser_key: str
    adapter_key: str
    verified: bool
    fetcher_key: str = "http"


_PROFILES = {
    "LOTERIA_CUNDINAMARCA": TraditionalLotterySource(
        "Lotería de Cundinamarca — resultados",
        "https://loteriadecundinamarca.com.co/",
        "traditional_result_page_embedded",
        "traditional_four_digit_series",
        True,
        fetcher_key="same_origin_iframe",
    ),
    "LOTERIA_TOLIMA": TraditionalLotterySource(
        "Lotería del Tolima — resultados",
        "https://loteriadeltolima.com/resultados/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_CRUZ_ROJA": TraditionalLotterySource(
        "Lotería de la Cruz Roja — resultados",
        "https://lotecruz.org.co/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_HUILA": TraditionalLotterySource(
        "Lotería del Huila — sorteos",
        "https://loteriadelhuila.com/category/sorteos/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_MANIZALES": TraditionalLotterySource(
        "Lotería de Manizales — resultados",
        "https://loteriademanizales.com/",
        "traditional_result_page",
        "traditional_four_digit_series",
        False,  # Official results are dynamically rendered; parser endpoint not yet verified.
    ),
    "LOTERIA_VALLE": TraditionalLotterySource(
        "Lotería del Valle — resultados",
        "https://loteriadelvalle.com/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_META": TraditionalLotterySource(
        "Lotería del Meta — fuente primaria pendiente",
        None,
        "traditional_result_page",
        "traditional_four_digit_series",
        False,
    ),
    "LOTERIA_BOGOTA": TraditionalLotterySource(
        "Lotería de Bogotá — resultados",
        "https://institucional.loteriadebogota.com/resultados/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_QUINDIO": TraditionalLotterySource(
        "Lotería del Quindío — resultados",
        "https://www.loteriaquindio.com.co/consultar_sorteo",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_MEDELLIN": TraditionalLotterySource(
        "Lotería de Medellín — resultados",
        "https://loteriademedellin.com.co/resultados/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_SANTANDER": TraditionalLotterySource(
        "Lotería Santander — resultados",
        "https://loteriasantander.gov.co/resultados/",
        "traditional_result_page",
        "traditional_four_digit_series",
        False,  # Official result payload/endpoint not yet verified for this adapter.
    ),
    "LOTERIA_RISARALDA": TraditionalLotterySource(
        "Lotería de Risaralda — resultados",
        "https://ventas.loteriadelrisaralda.com/resultados",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_BOYACA": TraditionalLotterySource(
        "Lotería de Boyacá — resultados",
        "https://loteriadeboyaca.gov.co/resultados/",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "LOTERIA_CAUCA": TraditionalLotterySource(
        "Lotería del Cauca — resultados",
        "https://www.loteriadelcauca.gov.co/la-loteria/ultimos-resultados",
        "traditional_result_page",
        "traditional_four_digit_series",
        True,
    ),
    "EXTRA_COLOMBIA": TraditionalLotterySource(
        "Sorteo Extraordinario de Colombia — fuente primaria pendiente",
        None,
        "traditional_result_page",
        "traditional_four_digit_series",
        False,
    ),
}


def get_traditional_source(code: str) -> TraditionalLotterySource:
    try:
        return _PROFILES[code.upper()]
    except KeyError as exc:
        raise KeyError(f"No traditional lottery source configured for {code}") from exc
