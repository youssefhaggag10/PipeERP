from pathlib import Path

import pytest
from app.core.app_paths import AppPaths
from app.database.connection import Database
from app.database.schema import initialize_database
from app.models.user import User
from app.repositories.admin_only_crm_repository import AdminOnlyCRMRepository
from app.repositories.strict_product_repository import StrictProductRepository
from app.services.recipe_scrap_cost_service import estimate_recipe_scr