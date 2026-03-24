"""Layout smoke tests for StatusStrip (Sprint 2 / P0-S1)."""

def test_status_strip_simple_hides_storage_and_phase_primary_color():
    import ttkbootstrap as tb

    from dedup.ui.shell.status_strip import StatusStrip

    root = tb.Window(themename="darkly")
    root.withdraw()
    try:
        strip = StatusStrip(root)
        root.update_idletasks()
        assert strip._cells["storage"].winfo_manager() == "pack"

        strip.set_ui_mode("simple")
        root.update_idletasks()
        assert strip._cells["storage"].winfo_manager() == ""
        assert strip._cells["intent"].winfo_manager() == ""

        strip.set_ui_mode("advanced")
        root.update_idletasks()
        assert strip._cells["storage"].winfo_manager() == "pack"
        assert strip._cells["intent"].winfo_manager() == "pack"

        strip.update_session("abc123", "Hashing", engine_health="Healthy", warnings=0)
        t = strip._tm.tokens
        assert strip._labels["phase"].cget("foreground") == t["text_primary"]
    finally:
        root.destroy()
