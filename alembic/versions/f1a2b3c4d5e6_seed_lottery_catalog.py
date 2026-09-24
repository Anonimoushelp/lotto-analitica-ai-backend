"""Seed the lottery catalog required by the ingestion sources.

Revision ID: f1a2b3c4d5e6
Revises: e5a1c7d9f2b4
"""

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5a1c7d9f2b4"
branch_labels = None
depends_on = None


LOTTERIES = (
    ("MILOTO", "MiLoto", "Colombia"),
    ("BALOTO", "Baloto", "Colombia"),
    ("REVANCHA", "Baloto Revancha", "Colombia"),
    ("SUPER_ASTRO", "Super Astro", "Colombia"),
    ("ANTIOQUENITA", "Antioqueñita", "Colombia"),
    ("CHONTICO", "Chontico", "Colombia"),
    ("DORADO", "El Dorado", "Colombia"),
    ("CAFETERITO", "Cafeterito", "Colombia"),
    ("PAISITA", "Paisita", "Colombia"),
    ("FANTASTICA", "Fantástica", "Colombia"),
    ("LOTERIA_CUNDINAMARCA", "Lotería de Cundinamarca", "Colombia"),
    ("LOTERIA_TOLIMA", "Lotería del Tolima", "Colombia"),
    ("LOTERIA_CRUZ_ROJA", "Lotería Cruz Roja", "Colombia"),
    ("LOTERIA_HUILA", "Lotería del Huila", "Colombia"),
    ("LOTERIA_MANIZALES", "Lotería de Manizales", "Colombia"),
    ("LOTERIA_VALLE", "Lotería del Valle", "Colombia"),
    ("LOTERIA_META", "Lotería del Meta", "Colombia"),
    ("LOTERIA_BOGOTA", "Lotería de Bogotá", "Colombia"),
    ("LOTERIA_QUINDIO", "Lotería del Quindío", "Colombia"),
    ("LOTERIA_MEDELLIN", "Lotería de Medellín", "Colombia"),
    ("LOTERIA_SANTANDER", "Lotería de Santander", "Colombia"),
    ("LOTERIA_RISARALDA", "Lotería de Risaralda", "Colombia"),
    ("LOTERIA_BOYACA", "Lotería de Boyacá", "Colombia"),
    ("LOTERIA_CAUCA", "Lotería del Cauca", "Colombia"),
    ("EXTRA_COLOMBIA", "Extra de Colombia", "Colombia"),
)


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO lotteries (code, name, country, active, created_at, updated_at)
        VALUES
        """
        + ",\n".join(
            f"('{code}', '{name.replace("'", "''")}', '{country}', TRUE, NOW(), NOW())"
            for code, name, country in LOTTERIES
        )
        + """
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    # Catalog rows may already be referenced by persisted draws; do not delete
    # production data during a migration rollback.
    pass
