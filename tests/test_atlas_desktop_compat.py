"""ATLAS desktop public imports remain compatible across the product rename."""

import pytest


@pytest.mark.unit
def test_old_and_new_system_tray_symbols_reference_the_same_class():
    from desktop_app import JarvisSystemTray
    from desktop_app.app import ATLASSystemTray, JarvisSystemTray as LegacyTray

    assert LegacyTray is ATLASSystemTray
    assert JarvisSystemTray is ATLASSystemTray


@pytest.mark.unit
def test_desktop_module_entry_point_imports_after_rename():
    from desktop_app import main
    from desktop_app.__main__ import main as module_main

    assert callable(main)
    assert callable(module_main)
