from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from technical_document_ml_service.db.init_db import seed_initial_data
from technical_document_ml_service.db.session import SessionLocal

LOGGER = logging.getLogger(__name__)

# parents[3]: migrate.py - db/ - technical_document_ml_service/ - src/ - /app/
_ALEMBIC_CFG_PATH = Path(__file__).parents[3] / "alembic.ini"


def _run_migrations() -> None:
    cfg = Config(str(_ALEMBIC_CFG_PATH))
    command.upgrade(cfg, "head")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        stream=sys.stdout,
    )

    LOGGER.info("Applying database migrations...")
    try:
        _run_migrations()
    except Exception:
        LOGGER.exception("Migration failed")
        sys.exit(1)
    LOGGER.info("Migrations applied successfully")

    LOGGER.info("Seeding initial data...")
    try:
        with SessionLocal.begin() as session:
            seed_initial_data(session)
    except Exception:
        LOGGER.exception("Seeding failed")
        sys.exit(1)
    LOGGER.info("Initial data seeded successfully")


if __name__ == "__main__":
    main()
