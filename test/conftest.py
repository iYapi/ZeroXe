"""Pytest test configuration and isolated QSettings fixture."""

import os
from pathlib import Path
import pytest
from PySide6.QtCore import QSettings

from zeroxe import config
from zeroxe.services.pipeline_service import PipelineService
from zeroxe.services.settings_service import SettingsService


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path, monkeypatch):
    """Ensure all tests run with an isolated QSettings environment without polluting user config."""
    ini_file = str(tmp_path / "test_settings.ini")
    test_settings = QSettings(ini_file, QSettings.Format.IniFormat)

    # Monkeypatch SettingsService._settings to return our test instance
    monkeypatch.setattr(SettingsService, "_settings", classmethod(lambda cls: test_settings))

    # Clear pipeline caches before and after each test
    PipelineService.clear_cache()

    yield test_settings

    PipelineService.clear_cache()
