from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


class AppPaths:
    """Resolve writable per-user paths and migrate legacy project data safely."""

    APP_DIR_NAME = "PipeERP"
    DATA_OVERRIDE_ENV = "PIPEERP_DATA_DIR"
    PORTABLE_MODE_ENV = "PIPEERP_PORTABLE_MODE"
    MIGRATION_MARKER = ".legacy-migration-complete"

    @classmethod
    def project_root