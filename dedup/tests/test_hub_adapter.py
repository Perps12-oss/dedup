"""
Integration tests for ProjectionHubStoreAdapter: hub callbacks update UIStateStore.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Callable

import tkinter as tk

import pytest

from dedup.ui.projections.compatibility_projection import EMPTY_COMPAT
from dedup.ui.projections.metrics_projection import EMPTY_METRICS
from dedup.ui.projections.session_projection import EMPTY_SESSION
from dedup.ui.state.hub_adapter import ProjectionHubStoreAdapter
from dedup.ui.state.store import UIStateStore


class FakeHub:
    """Minimal hub with subscribe/publish (callbacks invoked synchronously, like tests on Tk thread)."""

    def __init__(self) -> None:
        self._subs: dict[str, list] = defaultdict(list)

    def subscribe(self, kind: str, cb) -> Callable[[], None]:
        self._subs[kind].append(cb)

        def unsub() -> None:
            try:
                self._subs[kind].remove(cb)
            except ValueError:
                pass

        return unsub

    def publish(self, kind: str, payload) -> None:
        for cb in list(self._subs.get(kind, [])):
            cb(payload)


@pytest.fixture(scope="module")
def tk_root():
    """One Tk root for the module — multiple Tk() instances can fail on some CI/Python builds."""
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk unavailable: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


class TestProjectionHubStoreAdapter:
    def test_session_publishes_to_store(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        hub = FakeHub()
        adapter = ProjectionHubStoreAdapter(hub, store)
        adapter.start()
        sess = replace(EMPTY_SESSION, session_id="hub-test-1", status="running")
        hub.publish("session", sess)
        assert store.state.scan.session.session_id == "hub-test-1"
        assert store.state.scan.session.status == "running"
        adapter.stop()

    def test_terminal_flushes_pending_metrics(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        hub = FakeHub()
        adapter = ProjectionHubStoreAdapter(hub, store)
        adapter.start()
        m = replace(EMPTY_METRICS, files_discovered_total=42)
        hub.publish("metrics", m)
        assert store.state.scan.metrics.files_discovered_total != 42  # coalesced, not yet flushed
        term = replace(EMPTY_SESSION, session_id="done-1", status="completed")
        hub.publish("terminal", term)
        assert store.state.scan.metrics.files_discovered_total == 42
        assert store.state.scan.terminal.session_id == "done-1"
        adapter.stop()

    def test_compat_and_events_log(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        hub = FakeHub()
        adapter = ProjectionHubStoreAdapter(hub, store)
        adapter.start()
        hub.publish("compatibility", EMPTY_COMPAT)
        hub.publish("events_log", ["a", "b"])
        assert store.state.scan.compat == EMPTY_COMPAT
        assert store.state.scan.events_log == ["a", "b"]
        adapter.stop()

    def test_stop_unsubscribes_without_error(self, tk_root):
        store = UIStateStore(tk_root=tk_root)
        hub = FakeHub()
        adapter = ProjectionHubStoreAdapter(hub, store)
        adapter.start()
        adapter.stop()
        adapter.stop()  # idempotent
