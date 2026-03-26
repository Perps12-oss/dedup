from dedup.services.adapters.runtime_adapter import RuntimeAdapter
from dedup.services.adapters.theme_manager_adapter import ThemeManagerAdapter
from dedup.ui.theme.theme_manager import get_theme_manager


class _C:
    def get_recent_folders(self):
        return ["x"]

    def get_history(self, limit=50):
        return []

    def get_resumable_scan_ids(self):
        return []


def test_runtime_adapter():
    r = RuntimeAdapter(_C())
    assert r.get_recent_folders() == ["x"]


def test_theme_manager_adapter_tokens():
    ad = ThemeManagerAdapter(get_theme_manager())
    tok = ad.get_tokens()
    assert "bg_base" in tok.as_dict()
