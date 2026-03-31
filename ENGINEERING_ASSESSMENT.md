# CEREBRO (dedup) — Engineering Assessment

**Date:** March 31, 2026
**Codebase:** ~25,300 lines Python | 135 files | 134 tests
**Architecture:** CustomTkinter GUI | SQLite persistence | Threaded scan engine

---

## 1. System Architecture Assessment

### Layer Stack

```
┌──────────────────────────────────────┐
│  UI  (dedup/ui/)                     │  CTK pages, controllers, projections
├──────────────────────────────────────┤
│  Application  (dedup/application/)   │  Thin service facades for UI
├──────────────────────────────────────┤
│  Orchestration  (dedup/orchestration/)│  Scan lifecycle, EventBus, Worker
├──────────┬───────────────────────────┤
│  Engine  │  Infrastructure           │  Duplicate detection | Persistence
│  (engine/)│  (infrastructure/)       │  Models, repos, migrations
└──────────┴───────────────────────────┘
          dedup/core/  —  Primitives (DI, Observable, Command)
          dedup/models/ — UI-only view model shapes
```

**Verdict: Clean layered architecture.** Dependency direction is strictly downward.
- Engine has zero UI imports ✓
- No circular dependencies detected ✓
- Business rules isolated in engine/ ✓
- All persistence flows through repositories — no raw SQL in business logic ✓
- EventBus properly bridges orchestration → UI ✓

### Accepted Trade-off
`CerebroCTKApp` is the composition root and legitimately instantiates `ScanCoordinator`.
Pages receive services only — not the coordinator. This is architecturally correct.

---

## 2. Repository Structure Review

```
dedup/
├── application/    (3 files)  — Service facades
├── core/           (4 files)  — DI, Observable, Command primitives
├── engine/         (13 files) — Duplicate detection algorithms
│   └── interfaces/ (2 files)  — Protocol definitions
├── infrastructure/ (25 files) — Persistence, migrations, config, logging
│   ├── repositories/ (13 files)
│   └── migrations/  (8 SQL + runner)
├── models/         (4 files)  — UI-only view models (mission, theme)
├── orchestration/  (3 files)  — ScanCoordinator, Worker, EventBus
├── ui/             (49 files) — CTK shell, pages, state, theme
└── tests/          (29 files) — 134 test functions
```

**Strengths:** Logical grouping, discoverable, good consistency.

**Cleanup opportunities:**
- `dedup/ui/shell/` — may still exist as empty directory (verify)
- `infrastructure/ui_settings.py:44–45` — two dead fields: `sun_valley_shell` (bool) and `win_mica_backdrop` (bool) stored but never read anywhere in the codebase

---

## 3. Code Quality Findings

### Most Complex Files

| File | Lines | Concern |
|------|-------|---------|
| `engine/pipeline.py` | 1,294 | Largest file; single cohesive responsibility (scan lifecycle) |
| `ui/ctk_app.py` | 916 | **40 methods** — theme, navigation, geometry, state sync, shortcuts, degradation all in one class |
| `ui/projections/hub.py` | 727 | Large but focused (event → UI state bridge) |
| `orchestration/worker.py` | `_run()` 145 lines | God function: thread lifecycle + pipeline + callbacks + error handling |

### Top Slop Patterns

**1. Repeated deletion-outcome logging (5× copy-paste)**
`engine/deletion.py` lines 498, 510, 524, 557, 564 — identical structure:
```python
result.failed_files.append({"path": file_path, "error": err})
if self.persistence:
    self.persistence.deletion_audit_repo.log(plan_id=..., file_id=path_to_id.get(file_path), ...)
```
→ Extract `_log_deletion_outcome(path, success, outcome, error)`.

**2. Plan groups use raw dicts instead of dataclasses**
`engine/deletion.py` lines 635–651: nested `dict` for `DeletionGroup`/`DeletionTarget`
with 12–15 `.get()` calls downstream. Should be `@dataclass`.

**3. Deep nesting in resume orchestration**
`engine/pipeline.py:640–651`: 9 levels of nesting. Extract inner conditionals.

**4. `CerebroCTKApp` SRP violation**
`ui/ctk_app.py:49` — 40 methods, 916 lines, mixed responsibilities:
theme management, page routing, window geometry, keyboard shortcuts, state sync,
toast notifications, degradation banners. Extract focused controllers.

**5. `orchestration/worker._run()` god function (145 lines)**
Manages thread lifecycle, pipeline execution, cancellation, callbacks, and error handling
in one method. Extract `_handle_pipeline_result()` and `_handle_pipeline_error()`.

**6. Duplicate `_update_label_colors()` across 6 pages**
`review_page.py`, `diagnostics_page.py`, `history_page.py`, `mission_page.py`,
`settings_page.py`, `welcome_page.py` — same recursive recoloring loop in each.
→ Extract to `ui/utils/theme_utils.py` as `apply_label_colors(widget, fg)`.

**7. Duplicate `panel` variable assignment**
`ui/ctk_pages/welcome_page.py:61` and `:64` — identical assignment, second is dead.

---

## 4. Bug Risk Analysis

### Active Bugs (Confirmed)

| Severity | Location | Issue |
|----------|----------|-------|
| **HIGH** | `engine/grouping.py:465` | `cancel_check=cancel_check` passed to `FullHashReducer.reduce()` which doesn't accept it → `TypeError` on any cancellation during full-hash phase |
| **HIGH** | `engine/grouping.py:417–425` | `keeper_file_id` can silently be `None` → potential DB constraint violation |
| **MEDIUM** | `engine/hashing.py:318–336` | TOCTOU: `path.exists()` check then `open()` without lock → `FileNotFoundError` on active filesystems |
| **MEDIUM** | `engine/deletion.py:505` | `file_id=path_to_id.get(file_path)` can be `None` → audit row with NULL file_id |
| **MEDIUM** | `ui/projections/hub.py:195–196` | `shutdown()` sets `_alive=False` but doesn't call `after_cancel()` → stale timer fires |
| **MEDIUM** | `ui/ctk_pages/themes_page.py:79` | `subscribe()` without unsubscribe → accumulating dead callbacks in ThemeManager singleton |
| **LOW** | `engine/deletion.py:47–49` | AppleScript escaping skips newlines/tabs → potential injection on macOS with adversarial filenames |

### Risk Patterns (Systemic)

- **60+ bare `except Exception`** across engine and UI — most log, some don't.
  Critical un-logged locations: `pipeline.py:670,745,1098`, `discovery.py:235`.
- **No DB file permission restriction** — database world-readable under default umask.

---

## 5. Performance Bottlenecks

| Risk | Location | Impact |
|------|----------|--------|
| **Missing SQL indexes** | All inventory queries | O(n) table scan per query at scale |
| **Size grouping holds all files in RAM** | `grouping.py:112–133` | OOM risk at 1M+ uniform-size files |
| **6× LIKE patterns per directory query** | `inventory_repo.py:104–120` | Slow on NFS; no index coverage |
| `path.exists()` before open (NFS round-trip) | `hashing.py:270`, `deletion.py:149` | Redundant network RTT |
| Multiple `ThreadPoolExecutor` instances | `hashing.py:403` | Thread over-allocation without global cap |

**Well-optimized (no action needed):**
- Discovery uses streaming generators — constant memory ✓
- mmap for files >1MB ✓
- Hash caching (in-memory + external) ✓
- Chunked `IN` queries (400-item batches) ✓
- Checkpoint/resume prevents unbounded scan memory growth ✓

---

## 6. Scalability Risks

| Scenario | Bottleneck | Severity |
|----------|-----------|----------|
| 1M+ files, uniform size | `size_groups` dict holds all `FileMetadata` in RAM | HIGH |
| Network filesystem | LIKE path matching × 6; `exists()` before every hash | MEDIUM |
| No inventory path index | Full table scan per phase lookup | MEDIUM |
| SQLite `IN` clause >999 params | Chunked at 400 — safe, but adds queries | LOW |
| Many concurrent scans | Single DB connection with threading.Lock — serialized | LOW |

---

## 7. Technical Debt Map

| Debt | Location | Severity | Age |
|------|----------|----------|-----|
| Raw dicts for deletion plan groups | `deletion.py:635–690` | MEDIUM | Old |
| `sun_valley_shell` / `win_mica_backdrop` unused settings | `ui_settings.py:44–45` | LOW | Post-migration |
| `TODO_POST_PHASE3.md` open items | `docs/` | LOW | Documented |
| `# type: ignore` pragmas (9 total) | Various | LOW | Justified |
| Broad `except Exception` (60+) | Engine + UI | MEDIUM | Systemic |
| `worker._run()` god function | `orchestration/worker.py:164` | MEDIUM | Growth debt |

**No hacks, no commented-out code blocks, no temp paths found.**
All migration scripts present and sequential (001–008). ✓

---

## 8. Testing and Reliability Review

### Coverage by Layer

| Layer | Test File(s) | Verdict |
|-------|-------------|---------|
| Pipeline | `test_pipeline.py` | Good — resume, phases, checkpoints covered |
| Deletion | `test_deletion_safety.py`, `test_critical_discovery_deletion.py` | Good — safety checks, audit log |
| Discovery | `test_discovery.py`, `test_incremental_discovery.py` | Good — streaming, incremental, merge |
| Hashing | `test_hashing.py` | Basic — cache hits; mmap path untested |
| Persistence | `test_persistence.py` | Good — schema, migrations, repos |
| Exception hygiene | `test_exception_hygiene.py` | Adequate |
| UI | `test_ctk_review_page.py`, `test_hub_adapter.py` | Basic |
| Grouping | `test_grouping_full_hash_reducer.py` | Minimal |

### Critical Gaps

- macOS AppleScript deletion path — **zero tests**
- Windows `winshell` trash path — **zero tests**
- Linux `gio trash` / `xdg-trash` — **zero tests**
- mmap hashing path (files >1MB) — **zero tests**
- Partial scan cancellation during full-hash phase — **zero tests** (and there's a TypeError bug here)
- Checkpoint recovery with corrupted data — **zero tests**
- Partial deletion (some files succeed, some fail) — **zero tests**

### Test Quality

- Assertions are specific and value-checked ✓
- No `assertTrue(True)` patterns ✓
- `test_controller_application_services.py` over-mocks — doesn't test real service integration

---

## 9. Security Concerns

| Issue | Severity | Location | Fix |
|-------|----------|----------|-----|
| AppleScript escaping misses `\n`, `\t` | MEDIUM | `deletion.py:47–49` | Escape all special chars or use POSIX file URL form |
| DB file lacks explicit permissions | MEDIUM | `persistence.py:88` | Add `db_path.chmod(0o600)` after creation |
| Audit log path not validated to be under app dir | LOW | `deletion.py:95–97` | Verify path is under `~/.dedup/` or XDG data dir |
| `_escape_posix_path_for_applescript` has no test | LOW | `deletion.py:47–49` | Add adversarial filename tests |

**No hardcoded secrets, no `shell=True` subprocess calls, no SQL injection vectors found.**

---

## 10. Improvement Roadmap

### Priority 1 — Critical Fixes (do now)

1. Fix `grouping.py:465` — add `cancel_check` param to `FullHashReducer.reduce()`
2. Guard `keeper_file_id is None` in `grouping.py:417`
3. Wrap `hash_full()` open in `try/except (FileNotFoundError, OSError)` — `hashing.py:336`
4. Store `after()` ID in `hub.py`; cancel in `shutdown()`
5. Add `unsubscribe` on destroy in `themes_page.py`
6. Fix AppleScript escaping for `\n`/`\t` in `deletion.py:47`
7. Add `db_path.chmod(0o600)` in `persistence.py`

### Priority 2 — Architectural Improvements

1. Add missing SQL indexes (session_id, path, size_bytes) via migration 009
2. Extract `DeletionGroup` / `DeletionTarget` dataclasses from raw dicts
3. Break `CerebroCTKApp` into `ThemeController`, `NavigationController`, `WindowGeometryManager`
4. Refactor `worker._run()` — extract result/error handlers
5. Remove unused `sun_valley_shell` and `win_mica_backdrop` from `AppSettings`

### Priority 3 — Performance Enhancements

1. Memory-aware chunking in `grouping.py` size-group phase for 1M+ file datasets
2. Replace `path.exists()` pre-checks with try-open patterns (eliminates NFS round-trip)
3. Normalize paths at write-time to eliminate 6× LIKE query per directory lookup

### Priority 4 — Code Quality Cleanup

1. Extract `_log_deletion_outcome()` helper in `deletion.py` (removes 5× duplication)
2. Extract `apply_label_colors()` shared utility (removes 6× page duplication)
3. Add `_log.warning()` to silent `except Exception: pass` blocks (key locations: `pipeline.py:670,745,1098`)
4. Name magic-number constants in `hashing.py` (1MB mmap threshold, 32MB large-file threshold)
5. Remove duplicate `panel` assignment in `welcome_page.py:64`
6. Add DI container reset fixture to `conftest.py`
7. Add `pytest-cov` to `requirements-dev.txt`; constrain `>=` pins

---

## 11. Refactor Recommendations

### R1: `DeletionGroup` / `DeletionTarget` dataclasses
Replace `dict` plan groups (15+ `.get()` calls) with typed dataclasses.
File: `engine/deletion.py:635–690`
Impact: Type safety, IDE completion, -50 LOC in consumers.

### R2: Extract `_log_deletion_outcome()` in `DeletionEngine`
Consolidate 5 identical error-logging blocks into one method.
File: `engine/deletion.py`
Impact: -40 LOC, single fix point for audit log format changes.

### R3: Decompose `CerebroCTKApp`
Extract to dedicated controllers:
- `ThemeController` — token propagation, theme apply (lines 124–216)
- `NavigationController` — page routing, nav button sync (lines 218–239)
- `WindowGeometryManager` — geometry persistence (lines 137–151)
File: `ui/ctk_app.py`
Impact: -200 LOC in shell, SRP compliance, testable units.

### R4: Refactor `worker._run()` into sub-methods
Extract:
- `_handle_result(result)` — event publishing, callback invocation on success
- `_handle_error(exc)` — error callback, logging, diagnostics
File: `orchestration/worker.py:164`
Impact: -80 LOC in `_run()`, readable control flow.

### R5: Add SQL index migration (009)
```sql
CREATE INDEX IF NOT EXISTS idx_inv_session_path ON inventory_files(session_id, path);
CREATE INDEX IF NOT EXISTS idx_inv_session_size ON inventory_files(session_id, size_bytes);
```
File: `infrastructure/migrations/009_inventory_indexes.sql`
Impact: O(log n) vs O(n) for inventory lookups at scale.

### R6: Extract `apply_label_colors()` theme utility
Consolidate 6-page duplicate `_update_label_colors()` into `ui/utils/theme_utils.py`.
Impact: Single fix point for label recoloring behavior.

---

## 12. Engineering Health Score

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Architecture** | **9/10** | Clean layered design, strict dependency direction, no circular imports, event-driven UI bridge |
| **Code Quality** | **6/10** | Good naming and types; penalized for god class (ctk_app), god function (worker._run), raw-dict plan groups, 5× duplication in deletion |
| **Performance** | **7/10** | Well-optimized hot paths (streaming, mmap, caching); penalized for missing indexes and unbounded RAM in size-grouping |
| **Maintainability** | **7/10** | Good docs and structure; penalized for 1,294-line pipeline, 916-line ctk_app, 60+ broad excepts |
| **Reliability** | **7/10** | Strong test suite; penalized for `cancel_check` crash bug, TOCTOU race, theme subscription leak, zero platform-specific deletion tests |

### Overall: 7.2 / 10

**Strengths:** Excellent layering, clean event architecture, comprehensive persistence with migrations, good threading model, meaningful test suite.

**Top 3 actions to raise the score:**
1. Fix the `cancel_check` TypeError (Reliability 7 → 8)
2. Add SQL indexes and fix grouping memory (Performance 7 → 8)
3. Decompose `CerebroCTKApp` and extract deletion helpers (Code Quality 6 → 7)
