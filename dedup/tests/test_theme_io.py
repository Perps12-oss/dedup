from dedup.services.theme_io import THEME_EXPORT_FORMAT, build_export_payload, validate_import_format
from dedup.ui.theme.theme_config import ThemeConfig


def test_build_export_payload():
    tc = ThemeConfig(theme_key="cerebro_noir")
    p = build_export_payload(theme_key="cerebro_noir", theme_config=tc, ui_flags={"high_contrast": False})
    assert p["export_format"] == THEME_EXPORT_FORMAT
    assert p["theme_key"] == "cerebro_noir"


def test_validate_import_format():
    ok, _ = validate_import_format({"export_format": THEME_EXPORT_FORMAT})
    assert ok
    ok2, msg = validate_import_format({"export_format": "wrong"})
    assert not ok2
