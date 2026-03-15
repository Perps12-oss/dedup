# DEDUP Stress-Test & Hardening Audit Summary

## 1. Audit scope

- **Target scale:** ~1,000,000 files.
- **Focus:** Correctness, performance, truthfulness of metrics, safety of deletion, resume/cancel, UI responsiveness, failure handling, test coverage.

---

## 2. Risk list (by severity)

| Severity | Risk | Status |
|----------|------|--------|
| **Critical** | Discovery could hang (workers never signaled completion) | **Fixed:** Workers put a done-sentinel in result_queue; work_queue gets one SENTINEL per worker so workers eventually exit. |
| **Critical** | Reclaimable space shown before full-hash confirmation | **Verified:** Reclaimable is only summed from `DuplicateGroup.reclaimable_size`, which is computed from confirmed (full-hash) groups. |
| **High** | Partial hash (first 4KB only) weak for same-size non-duplicates | **Fixed:** Partial hash now uses first + middle + last chunks (size-aware sampling). |
| **High** | Deletion plan ignored user “Keep” selection in UI | **Fixed:** `create_plan_from_groups` accepts `group_keep_paths`; Results frame passes `selected_groups` and has “Keep this file” button. |
| **High** | `DeletionResult.bytes_reclaimed` never set | **Fixed:** Size is read before each delete and added to `bytes_reclaimed` on success. |
| **Medium** | Full file list materialized in memory (1M files) | **Documented:** Pipeline’s `_discover_files` returns `List[FileMetadata]`; grouping then holds candidates in memory. For 1M files this is a known memory spike; streaming grouping would require larger refactor. |
| **Medium** | Hash cache is in-memory only (not wired to DB) | **Fixed:** Coordinator passes `get_hash_cache`/`set_hash_cache` to worker → pipeline → `HashEngine`; hashing uses DB cache with size/mtime invalidation. |
| **Medium** | ResumableScanPipeline checkpoints never called | **Fixed:** Checkpoints saved after discovery; `run()` loads checkpoint when present and skips discovery; worker uses `ResumableScanPipeline` when `checkpoint_dir` set; History offers "Resume Scan" for resumable scan_ids. |
| **Low** | Persistence `get_default_persistence` used `sys` before import | **Fixed:** `sys` imported at top of `persistence.py`. |
| **Low** | Coordinator missing `DeletionPolicy` import | **Fixed.** |
| **Low** | Results tree could be huge (no virtualization) | **Documented:** Tree adds all groups; for very large result sets consider pagination/virtualization. |

---

## 3. Truthfulness audit

- **Candidates vs confirmed:** Only groups that pass full-hash confirmation are shown as duplicate groups; reclaimable bytes are only from those groups. **OK.**
- **Progress:** `ScanProgress.percent_complete` is `None` when `files_total` is `None`. Scan frame uses indeterminate progress bar. **OK.**
- **ETA:** `estimated_remaining_seconds` is only set when meaningful; UI does not show fake ETA. **OK.**
- **Reclaimable:** Not double-counted; each group’s `reclaimable_size = file_size * (n - 1)`. **OK.**
- **Metric semantics:** `engine/metrics_semantics.py` defines and documents all metric names and when percent/ETA are valid.

---

## 4. Code and behavior changes made

1. **engine/discovery.py**
   - Completion: workers put a sentinel (`_WORKER_DONE`) into `result_queue` on exit; main loop counts these and exits when all workers done.
   - Work termination: one SENTINEL per worker is added to `work_queue` at start so workers eventually see SENTINEL and exit.
   - Exception handling: broad `except Exception` in worker loop; directory scan catches OSError/PermissionError and generic Exception.

2. **engine/hashing.py**
   - Partial hash: first + middle + last chunks (size-aware); still for candidate reduction only; confirmation always uses full hash.

3. **engine/deletion.py**
   - `execute_plan`: before each delete, `stat()` the file and add size to `bytes_reclaimed` on success.
   - `create_plan_from_groups`: added `group_keep_paths: Optional[Dict[str, str]]`; when set, used to choose which file to keep per group.

4. **orchestration/coordinator.py**
   - `create_deletion_plan`: accepts `group_keep_paths`, passes to deletion engine; fixed `DeletionPolicy` import.

5. **ui/pages/review_page.py** (replaced legacy results_frame.py)
   - “Keep this file” button and `_on_keep_this_file`: sets `selected_groups[group_id]` to selected file and refreshes list.
   - `_create_deletion_plan`: passes `group_keep_paths=self.selected_groups` so the plan matches user choices.

6. **infrastructure/persistence.py**
   - `sys` imported at top; `get_default_persistence` uses `sys.platform` correctly.

7. **engine/metrics_semantics.py** (new)
   - Defines metric names and semantics; `should_show_percent`, `should_show_eta` for UI/logic.

8. **engine/bench.py** (new)
   - Optional bench collector (env `DEDUP_BENCH=1`): phase timings, counts, rates; for logs/tests only, not user UI.

---

## 5. Test suite

- **Location:** `tests/`
- **Run (from repo root, with dedup on PYTHONPATH):**
  ```bash
  cd path/to/dedup
  python -m pytest tests -v --tb=short
  ```
  From the folder that *contains* the `dedup` package (e.g. parent of `dedup`), or ensure that folder is on `PYTHONPATH` so `from dedup.engine import ...` works.

- **Categories:**
  - **test_truthfulness.py:** Reclaimable from confirmed only; percent only with total; duplicate counts exact; metric semantics helpers.
  - **test_hashing.py:** Full hash used for confirmation; partial uses first+middle+last; different content same partial separated by full hash.
  - **test_discovery.py:** Yields files, respects min size, cancel, stats.
  - **test_deletion_safety.py:** Keep not in delete list; plan respects `group_keep_paths`; execute never deletes keep file.
  - **test_persistence.py:** Save/load scan, list scans, hash cache get/set; fixture closes persistence so temp DB can be removed.

- **Persistence tests:** Use a fixture that calls `persistence.close()` in teardown to avoid “file in use” on Windows when deleting temp dir.

---

## 6. Dataset generator

- **Script:** `scripts/generate_stress_datasets.py`
- **Usage:**
  ```bash
  python scripts/generate_stress_datasets.py <output_dir> [--profile NAME] [--count N]
  ```
- **Profiles:** `many_small`, `many_large`, `mixed`, `same_size_non_dupes`, `true_duplicates`, `near_collision`, `deep_tree`, `unicode`, `all`.
- Use for manual or automated stress runs (e.g. duplicate counts, reclaimable bytes, memory, runtime).

---

## 7. Production readiness verdict

- **Duplicate detection:** Correct and conservative. Partial hash is for candidate reduction only; confirmation is full-file hash. No duplicate declared from partial hash alone.
- **Metrics:** Reclaimable and duplicate counts are truthful and only from confirmed groups. Progress can stay indeterminate when total is unknown.
- **Deletion:** Plan matches user keep selection; keep file is never deleted; bytes reclaimed is reported correctly.
- **Discovery:** Completion and cancellation behavior fixed; suitable for large runs.
- **Scale (1M files):** Main limitation is memory: full discovered file list and candidate lists are in memory. Acceptable for many deployments but not “O(1) memory”; consider streaming/chunking for future work.
- **Resume:** Implemented: checkpoint saved after discovery; resume from History for cancelled scans; only discovery phase is resumable (grouping/hashing re-run from cached file list).
- **Caveats:**
  - Very large result sets in the UI (e.g. 100k+ groups) may benefit from virtualization/pagination.
  - SQLite and temp file cleanup on Windows require closing connections/handles before deleting (handled in tests via fixture).
  - Image thumbnails require Pillow; app degrades gracefully if not installed.

**Verdict:** Production-usable for typical and large (hundreds of thousands of files) datasets. Safe for duplicate detection and deletion; metrics and UI are truthful and conservative. Resume, media filtering, thumbnails, empty-trash, and history roots/resume are implemented.

---

## 8. Run instructions for stress suite

1. **Unit/integration tests**
   - From the directory that contains the `dedup` package (e.g. parent of the `dedup` repo folder):
     ```bash
     python -m pytest dedup/tests -v --tb=short
     ```
   - Or from inside the repo if `PYTHONPATH` includes the parent of `dedup`:
     ```bash
     set PYTHONPATH=%CD%\..
     python -m pytest tests -v --tb=short
     ```

2. **Generate synthetic datasets**
   ```bash
   python scripts/generate_stress_datasets.py C:\path\to\stress_data --profile all
   python scripts/generate_stress_datasets.py C:\path\to\stress_data --profile same_size_non_dupes --count 2000
   ```

3. **Run a scan on generated data (CLI)**
   ```bash
   python -m dedup C:\path\to\stress_data -v
   ```

4. **Bench instrumentation (logs only)**
   ```bash
   set DEDUP_BENCH=1
   python -m dedup C:\path\to\stress_data -v
   ```
   Check log output for phase durations and rates (debug level).

---

## 9. Feature-completion pass (summary)

- **Checkpoint / resume:** `ResumableScanPipeline.run()` now saves a checkpoint after discovery and loads it when present; coordinator passes `checkpoint_dir` and optional `resume_scan_id`; History screen shows "Resume Scan" for scans with a checkpoint. Only the discovery phase is resumable (grouping/hashing re-run from the cached file list).
- **Persistent hash cache:** Already wired: coordinator passes `get_hash_cache`/`set_hash_cache` to the worker; pipeline assigns them to `HashEngine`; hashing reads/writes DB cache with size/mtime invalidation.
- **Media filtering:** `engine/media_types.py` added (Images, Videos, Audio, Documents, Archives, All); Home screen has a "File type" dropdown; coordinator maps `media_category` to `allowed_extensions` for discovery.
- **Image thumbnails:** `engine/thumbnails.py` added (Pillow, disk cache, async generation); Results frame shows a thumbnail strip for image duplicate groups; graceful fallback when Pillow is not installed.
- **Empty Trash:** `infrastructure/trash.py` lists/empties the DEDUP fallback folder (`~/.dedup/trash`); History screen has "Empty Trash" with confirmation (file count and size). Does not affect system recycle bin.
- **History:** `list_scans` now includes `roots` (from stored config); History tree shows Roots column; "Resume Scan" button for resumable scans; "Load Selected" and "Delete Selected" unchanged.
- **Drag-and-drop:** Already present (tkinterdnd2; fallback to click-to-browse when unavailable). No change.
- **Progress UI:** Existing truthful behavior preserved (phase, files, groups, elapsed, current file; indeterminate bar; no fake ETA).

**Status after pass:** Core features are complete. Remaining limitations: full file list and candidate groups still materialized in memory (no O(1) claim); only discovery is resumable; thumbnails optional (Pillow). App is ready for typical use and for large scans with resume and hash cache; very large result sets (100k+ groups) may benefit from future UI virtualization.
