from app.sources.contracts import SourceSpec


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        lottery_code="MILOTO",
        draw_types=("MILOTO",),
        primary_name="Baloto",
        primary_url="https://baloto.com/miloto/resultados/",
        primary_verified=True,
        notes="Five main numbers.",
    ),
    SourceSpec(
        lottery_code="BALOTO",
        draw_types=("BALOTO",),
        primary_name="Baloto",
        primary_url="https://www.baloto.com/verificador-resultados",
        primary_verified=True,
        notes="Five main numbers plus Superbalota.",
    ),
    SourceSpec(
        lottery_code="REVANCHA",
        draw_types=("REVANCHA",),
        primary_name="Baloto",
        primary_url="https://www.baloto.com/verificador-resultados",
        primary_verified=True,
        notes="Five main numbers plus Revancha bonus number.",
    ),
    SourceSpec(
        lottery_code="SUPER_ASTRO",
        draw_types=("ASTRO_SOL", "ASTRO_LUNA"),
        primary_name="Super Astro",
        primary_url="https://www.superastro.com.co/index.php/resultados/historico-resultados",
        primary_verified=True,
        notes="Four-digit result; sign is preserved in metadata.",
    ),
    SourceSpec(
        lottery_code="ANTIOQUENITA",
        draw_types=("ANTIOQUENITA_1", "ANTIOQUENITA_2"),
        primary_name="Antioqueñita",
        primary_url=None,
        primary_verified=False,
        notes="Historical records located; primary source still pending final validation.",
    ),
    SourceSpec(
        lottery_code="CHONTICO",
        draw_types=("CHONTICO_DIA", "CHONTICO_NOCHE", "CHONTICO_SUPER_NOCHE"),
        primary_name="Chontico",
        primary_url=None,
        primary_verified=False,
        notes="Day, Night and Super Noche are separate draw types.",
    ),
    SourceSpec(
        lottery_code="DORADO",
        draw_types=("DORADO_DIA", "DORADO_TARDE", "DORADO_NOCHE"),
        primary_name="Paga Todo",
        primary_url="https://www.pagatodo.com.co/resultados-loto-core/sorteos/",
        primary_verified=False,
        notes="Four digits plus an additional value; its semantic role is not yet normalized as bonus/series.",
    ),
    SourceSpec(
        lottery_code="CAFETERITO",
        draw_types=("CAFETERITO_TARDE", "CAFETERITO_NOCHE"),
        primary_name="Cafeterito",
        primary_url=None,
        primary_verified=False,
        notes="Tarde and Noche are separate draw types; primary semantics pending final validation.",
    ),
    SourceSpec(
        lottery_code="PAISITA",
        draw_types=("PAISITA_DIA", "PAISITA_NOCHE"),
        primary_name="Paisita",
        primary_url=None,
        primary_verified=False,
        notes="Paisita Noche preserves the animal as metadata.",
    ),
    SourceSpec(
        lottery_code="FANTASTICA",
        draw_types=("FANTASTICA_DIA", "FANTASTICA_NOCHE"),
        primary_name="Fantástica",
        primary_url=None,
        primary_verified=False,
        notes="Day and Night exist; primary source validation remains pending.",
    ),
)

SOURCE_REGISTRY: dict[str, SourceSpec] = {
    spec.lottery_code: spec for spec in SOURCE_SPECS
}


def get_source_spec(lottery_code: str) -> SourceSpec:
    try:
        return SOURCE_REGISTRY[lottery_code.upper()]
    except KeyError as exc:
        raise KeyError(f"Unsupported lottery source: {lottery_code}") from exc


def is_draw_type_supported(lottery_code: str, draw_type: str) -> bool:
    return draw_type in get_source_spec(lottery_code).draw_types
