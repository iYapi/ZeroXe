import pytest
from PySide6.QtCore import QSettings

from zeroxe.views.settings_view import SettingsView


@pytest.fixture
def settings_view(qtbot, tmp_path, monkeypatch):
    # Isolate QSettings in controller
    ini_file = str(tmp_path / "test_settings_controller.ini")
    test_settings = QSettings(ini_file, QSettings.Format.IniFormat)
    monkeypatch.setattr(
        "zeroxe.controllers.setting_controller.QSettings",
        lambda *args, **kwargs: test_settings,
    )

    view = SettingsView()
    qtbot.addWidget(view)
    return view, test_settings


def test_settings_view_initialization(settings_view):
    view, _ = settings_view
    assert view.windowTitle() == "Settings"
    assert view.ui.listWidget_menu.count() == 3
    assert view.stack.count() == 3
    assert hasattr(view.software_ui, "lineEdit_blenderUrl")
    assert hasattr(view.software_ui, "pushButton_removeBlender")


def test_add_blender_path(settings_view):
    view, _ = settings_view
    ctrl = view.controller
    sw_ui = view.software_ui

    sw_ui.lineEdit_blenderUrl.setText("/path/to/blender-4.2")
    ctrl.on_add_blender()

    assert sw_ui.listWidget_blenderList.count() == 1
    assert sw_ui.listWidget_blenderList.item(0).text() == "/path/to/blender-4.2"
    assert sw_ui.lineEdit_blenderUrl.text() == ""
    assert sw_ui.lineEdit_selectedBlender.text() == "/path/to/blender-4.2"


def test_select_blender_path(settings_view):
    view, _ = settings_view
    ctrl = view.controller
    sw_ui = view.software_ui

    sw_ui.lineEdit_blenderUrl.setText("/path/to/blender-4.0")
    ctrl.on_add_blender()
    sw_ui.lineEdit_blenderUrl.setText("/path/to/blender-4.2")
    ctrl.on_add_blender()

    assert sw_ui.listWidget_blenderList.count() == 2
    item_40 = sw_ui.listWidget_blenderList.item(0)
    ctrl.on_blender_item_selected(item_40)
    assert sw_ui.lineEdit_selectedBlender.text() == "/path/to/blender-4.0"


def test_remove_blender_path(settings_view):
    view, _ = settings_view
    ctrl = view.controller
    sw_ui = view.software_ui

    sw_ui.lineEdit_blenderUrl.setText("/path/to/blender-4.0")
    ctrl.on_add_blender()
    sw_ui.lineEdit_blenderUrl.setText("/path/to/blender-4.2")
    ctrl.on_add_blender()

    # Select the first item and remove it
    sw_ui.listWidget_blenderList.setCurrentRow(0)
    ctrl.on_remove_blender()

    assert sw_ui.listWidget_blenderList.count() == 1
    assert sw_ui.listWidget_blenderList.item(0).text() == "/path/to/blender-4.2"


def test_save_and_load_settings(settings_view):
    view, settings = settings_view
    ctrl = view.controller
    sw_ui = view.software_ui

    sw_ui.lineEdit_blenderUrl.setText("/path/to/blender-4.2")
    ctrl.on_add_blender()
    sw_ui.lineEdit_pureref.setText("/path/to/pureref")

    ctrl.save_settings()

    assert settings.value("software/active_blender") == "/path/to/blender-4.2"
    assert settings.value("software/pureref_path") == "/path/to/pureref"
    assert settings.value("software/blender_paths") == ["/path/to/blender-4.2"]

    # Clear UI and reload
    sw_ui.listWidget_blenderList.clear()
    sw_ui.lineEdit_selectedBlender.clear()
    sw_ui.lineEdit_pureref.clear()

    ctrl.load_settings()
    assert sw_ui.listWidget_blenderList.count() == 1
    assert sw_ui.lineEdit_selectedBlender.text() == "/path/to/blender-4.2"
    assert sw_ui.lineEdit_pureref.text() == "/path/to/pureref"
