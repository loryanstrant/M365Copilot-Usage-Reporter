"""Programmatic Alembic migration runner (used on API startup and in scripts)."""
from __future__ import annotations

import logging
import os

from alembic import command
from alembic.config import Config

logger = logging.getLogger("migrate")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic_config() -> Config:
    cfg = Config(os.path.join(_PROJECT_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_PROJECT_ROOT, "alembic"))
    return cfg


def upgrade_to_head() -> None:
    """Run ``alembic upgrade head``. Safe to call repeatedly."""
    logger.info("Running database migrations to head...")
    command.upgrade(_alembic_config(), "head")
    logger.info("Migrations complete.")
