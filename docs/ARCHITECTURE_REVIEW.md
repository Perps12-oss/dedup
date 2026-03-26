# Architecture review (formalized)

## Data flow

1. **`CerebroCTKApp` (`ui/ctk_app.py`)** owns the CTk root, `ScanCoordinator`, `ProjectionHub`, `UIStateStore`, and `ProjectionHubStoreAdapter`.
2. **Events** flow `coordinator.event_bus` → `ProjectionHub` → store adapter → **`UIStateStore`**.
3. **Pages** read store via `attach_store` / selectors where applicable; **controllers** (`ScanController`, `ReviewController`) send intents and update store.
4. **Rule:** `dedup/engine` and `dedup/orchestration` do **not** import `dedup.ui` (verified by grep, Phase 1).

## Component hierarchy

- **Shell:** `CerebroCTKApp` — nav column, content host, cinematic backdrop, `GradientBar`, page stack in `ctk_pages/`.
- **Pages:** Welcome, Mission, Scan, Review, History, Diagnostics, Themes, Settings (CustomTkinter).
- **Shared:** `ToastManager`, controllers, projections, store; **ttk** widgets under `ui/components/` are test / `ReviewVM` helpers only (see `components/README.md`).

## Performance notes (known)

- Large scans materialize file lists in memory; Review navigator capped (`REVIEW_NAVIGATOR_MAX_ROWS`).
- **Virtual tree / virtualization:** Not implemented — see Phase 4 skip list in `docs/PHASE_ROLLOUT.md`.
- Benchmarks: `engine/bench.py`, baseline doc `docs/BENCHMARK_BASELINE.md`.

## Accessibility & “responsive”

- **Tkinter desktop:** “Responsive” = min window size, grid weights; CTK uses inset layout + max widths where set in `ctk_app` / pages.
- **WCAG:** Contrast helpers in `dedup/ui/theme/contrast.py` (Phase 2); full AA pass **planned** Phase 7.
