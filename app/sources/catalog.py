from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.sources.adapters import (
    BalotoAdapter,
    MiLotoAdapter,
    RevanchaAdapter,
    SuperAstroAdapter,
)
from app.sources.contracts import SourceAdapter
from app.sources.fetchers import HttpSourceFetcher
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
from app.sources.ingestion import SourceIngestionPipeline
from app.sources.orchestrator import IngestionJob
from app.sources.parsers import (
    BalotoResultPageParser,
    HtmlTableParser,
    MiLotoResultPageParser,
    PagaTodoResultPageParser,
    SuperAstroResultPageParser,
)
from app.sources.provider_parser_adapter import (
    HtmlProviderParserAdapter,
    ProviderParserAdapter,
)
from app.sources.provider_parsers import (
    BalotoFamilyJsonParser,
    MiLotoJsonParser,
    SuperAstroJsonParser,
)
from app.sources.registry import get_source_spec
from app.sources.traditional_lottery import get_traditional_source
from app.sources.traditional_lottery_components import (
    TraditionalLotteryAdapter,
    TraditionalLotteryHtmlParser,
)


@dataclass(frozen=True)
class IngestionSourceConfig:
    key: str
    lottery_code: str
    url: str
    interval_seconds: int
    pipeline_factory: Callable[[], SourceIngestionPipeline]
    enabled: bool


def _json_pipeline(parser: object, adapter: SourceAdapter) -> SourceIngestionPipeline:
    return SourceIngestionPipeline(
        fetcher=HttpSourceFetcher(),
        parser=ProviderParserAdapter(parser),
        adapter=adapter,
    )


def _four_digit_pipeline(parser: object, adapter: SourceAdapter) -> SourceIngestionPipeline:
    return _json_pipeline(parser, adapter)


def _traditional_pipeline(code: str) -> SourceIngestionPipeline:
    return SourceIngestionPipeline(
        fetcher=HttpSourceFetcher(),
        parser=TraditionalLotteryHtmlParser(code),
        adapter=TraditionalLotteryAdapter(code),
    )


def _astro_pipeline() -> SourceIngestionPipeline:
    return SourceIngestionPipeline(
        fetcher=HttpSourceFetcher(),
        parser=ProviderParserAdapter(SuperAstroJsonParser()),
        adapter=SuperAstroAdapter(),
    )


def _html_chontico_pipeline() -> SourceIngestionPipeline:
    return SourceIngestionPipeline(
        fetcher=HttpSourceFetcher(),
        parser=HtmlProviderParserAdapter(
            parser=HtmlTableParser(),
            allowed_draw_types={
                "CHONTICO_DIA",
                "CHONTICO_NOCHE",
                "CHONTICO_SUPER_NOCHE",
            },
        ),
        adapter=ChonticoAdapter(),
    )


def build_ingestion_catalog() -> tuple[IngestionJob, ...]:
    jobs: list[IngestionJob] = []

    specs = get_source_spec

    jobs.extend(
        [
            IngestionJob(
                key="miloto-primary-json",
                lottery_code="MILOTO",
                url=specs("MILOTO").primary_url or "",
                pipeline_factory=lambda: SourceIngestionPipeline(
                    fetcher=HttpSourceFetcher(),
                    parser=MiLotoResultPageParser(),
                    adapter=MiLotoAdapter(),
                ),
                interval_seconds=900,
                enabled=specs("MILOTO").primary_verified,
            ),
            IngestionJob(
                key="baloto-primary-json",
                lottery_code="BALOTO",
                url=specs("BALOTO").primary_url or "",
                pipeline_factory=lambda: SourceIngestionPipeline(
                    fetcher=HttpSourceFetcher(),
                    parser=BalotoResultPageParser(draw_type="BALOTO"),
                    adapter=BalotoAdapter(),
                ),
                interval_seconds=1800,
                enabled=specs("BALOTO").primary_verified,
            ),
            IngestionJob(
                key="revancha-primary-json",
                lottery_code="REVANCHA",
                url=specs("REVANCHA").primary_url or "",
                pipeline_factory=lambda: SourceIngestionPipeline(
                    fetcher=HttpSourceFetcher(),
                    parser=BalotoResultPageParser(draw_type="REVANCHA"),
                    adapter=RevanchaAdapter(),
                ),
                interval_seconds=1800,
                enabled=specs("REVANCHA").primary_verified,
            ),
            IngestionJob(
                key="super-astro-sol-primary",
                lottery_code="SUPER_ASTRO",
                url=specs("SUPER_ASTRO").primary_url or "",
                pipeline_factory=lambda: SourceIngestionPipeline(
                    fetcher=HttpSourceFetcher(),
                    parser=SuperAstroResultPageParser(draw_type="ASTRO_SOL"),
                    adapter=SuperAstroAdapter(),
                ),
                interval_seconds=900,
                enabled=specs("SUPER_ASTRO").primary_verified,
            ),
            IngestionJob(
                key="super-astro-luna-primary",
                lottery_code="SUPER_ASTRO",
                url=specs("SUPER_ASTRO").primary_url or "",
                pipeline_factory=lambda: SourceIngestionPipeline(
                    fetcher=HttpSourceFetcher(),
                    parser=SuperAstroResultPageParser(draw_type="ASTRO_LUNA"),
                    adapter=SuperAstroAdapter(),
                ),
                interval_seconds=900,
                enabled=specs("SUPER_ASTRO").primary_verified,
            ),
        ]
    )

    four_digit = (
        ("ANTIOQUENITA", AntioquenitaJsonParser, AntioquenitaAdapter),
        ("CHONTICO", ChonticoJsonParser, ChonticoAdapter),
        ("DORADO", PagaTodoResultPageParser, DoradoAdapter),
        ("CAFETERITO", CafeteritoJsonParser, CafeteritoAdapter),
        ("PAISITA", PaisitaJsonParser, PaisitaAdapter),
        ("FANTASTICA", FantasticaJsonParser, FantasticaAdapter),
    )
    for code, parser_type, adapter_type in four_digit:
        spec = specs(code)
        jobs.append(
            IngestionJob(
                key=f"{code.lower()}-primary-json",
                lottery_code=code,
                url=spec.primary_url or "",
                pipeline_factory=(
                    lambda p=parser_type, a=adapter_type, c=code: SourceIngestionPipeline(
                        fetcher=HttpSourceFetcher(),
                        parser=(
                            p(draw_types=get_source_spec(c).draw_types)
                            if c == "DORADO"
                            else ProviderParserAdapter(p())
                        ),
                        adapter=a(),
                    )
                ),
                interval_seconds=900,
                enabled=spec.primary_verified and spec.primary_url is not None,
            )
        )

    # The HTML variant is retained as a separate adapter/pipeline contract.
    # It is disabled until its primary endpoint is explicitly confirmed as
    # the table-producing endpoint.
    chontico = specs("CHONTICO")
    jobs.append(
        IngestionJob(
            key="chontico-html-primary",
            lottery_code="CHONTICO",
            url=chontico.primary_url or "",
            pipeline_factory=_html_chontico_pipeline,
            interval_seconds=900,
            enabled=False,
        )
    )

    for code in (
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
        "EXTRA_COLOMBIA",
    ):
        profile = get_traditional_source(code)
        jobs.append(
            IngestionJob(
                key=f"{code.lower()}-traditional-html",
                lottery_code=code,
                url=profile.result_url or "",
                pipeline_factory=lambda c=code: _traditional_pipeline(c),
                interval_seconds=3600,
                enabled=profile.verified and profile.result_url is not None,
            )
        )

    return tuple(jobs)
