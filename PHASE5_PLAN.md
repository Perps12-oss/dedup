# Phase 5 Implementation Plan

Phase 5 items are **optional / later** (see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) § Phase 5). This document turns them into a concrete implementation plan for when you choose to do them.

---

## 5.1 Streaming grouping

**Goal:** Avoid materializing the full discovered file list in memory; feed discovery output in batches into grouping so memory stays bounded per batch.

**Current behavior:**  
`ScanPipeline._discover_files()` collects all files into a list; `grouping.find_duplicates(iter(discovered_files), ...)` then consumes that list. For 1M files, the list is 1M `FileMetadata` in RAM.

**Target behavior:**
- Discovery yields batches (e.g. via `discovery.discover_batch(batch_size=50000)`).
- Pipeline feeds each batch into grouping **incrementally**.
- Grouping must support incremental input: e.g. maintain size groups across batches, then run partial/full hash only on candidates that survive size grouping over the **full** dataset.

**Design choices:**
1. **Two-pass option:**  
   - Pass 1: discovery only, write (path, size, mtime_ns) to a temp SQLite table or streamed file.  
   - Pass 2: query/read only size groups with count ≥ 2, then load those paths for partial/full hash.  
   - Pro: true streaming, no full list in memory. Con: two passes, temp storage.

2. **Batch-merge option:**  
   - Grouping maintains `size_groups: Dict[int, List[FileMetadata]]` and accepts `add_batch(files)`.  
   - After all batches added, run existing partial/full hash on `size_groups`.  
   - Pro: minimal API change. Con: size groups still grow with file count (only paths/size/mtime, not full content).

3. **Hybrid:**  
   - Use temp SQLite for (path, size, mtime_ns) during discovery; then build size groups by querying DB (GROUP BY size HAVING COUNT(*) > 1), then load only those paths for hashing.  
   - Reuse existing hash cache and grouping logic.

**Recommended order:**  
- Implement **5.1a:** use `discover_batch()` in pipeline and merge batches into a single list for grouping (reduces peak only if we process and discard batches before merging—otherwise same memory).  
- Implement **5.1b:** temp DB or batch-merge so that we never hold more than N `FileMetadata` in memory (e.g. 50k per batch + only candidates for hashing).

**Acceptance:**  
- Scan over 500k+ files: peak RSS does not scale linearly with file count (e.g. stays under a target like 500 MB with bounded batch size).
- All existing tests pass; add one integration test that runs a large synthetic scan and asserts memory or batch count.

---

## 5.2 Results tree virtualization

**Goal:** For 100k+ duplicate groups, avoid loading every row into the Treeview; show a windowed subset and fetch on scroll.

**Current behavior:**  
[results_frame.py](dedup/ui/results_frame.py) inserts every group into `ttk.Treeview` in `_populate_tree()`. Large result sets make the UI slow or unresponsive.

**Target behavior:**
- Treeview shows a fixed window of groups (e.g. first 200).
- On scroll (or “Load more”), append the next 200 from `current_result.duplicate_groups`.
- Alternatively: replace Treeview with a scrollable list of frames and only create widgets for visible + buffer (true virtual list).

**Design choices:**
1. **Lazy load by range:**  
   Keep Treeview; maintain `displayed_count`; on scroll near bottom or “Load more” button, insert next N items from `duplicate_groups[displayed_count:displayed_count+N]`.

2. **Virtual list (no Treeview):**  
   Canvas or Frame with scrollbar; only create child frames for indices in `[scroll_top, scroll_top + visible_count + buffer]`; update on scroll. More work, best for 100k+ rows.

3. **Pagination:**  
   “Page 1 of 500” with prev/next; one page = e.g. 100 groups. Simplest, no scroll-based virtualization.

**Recommended order:**  
- **5.2a:** Add pagination (page size 100–200, prev/next). Easiest and improves UX for large sets.  
- **5.2b:** If needed, add lazy “Load more” at bottom of current Treeview.  
- **5.2c:** Only if required, implement full virtual list with Canvas/Frame.

**Acceptance:**  
- 10k groups: UI stays responsive; 100k groups: usable (pagination or virtual window).
- No change to engine or result structure; only UI presentation.

---

## 5.3 Cross-platform CI

**Goal:** Run the test suite automatically on Windows, macOS, and Linux (e.g. GitHub Actions).

**Current state:**  
No `.github/workflows`; tests are run manually.

**Target behavior:**
- On push/PR to `main` (and optionally to `refactor/phase-1-align-config-docs`): run `python -m pytest dedup/tests -q` on Windows, macOS, and Linux.
- Optional: run with optional deps (xxhash, send2trash) so hash and deletion tests use real implementations.
- No flaky tests; symlink test already skipped when unsupported.

**Steps:**
1. Add `.github/workflows/tests.yml`:
   - Trigger: push to main, pull_request to main (and optionally refactor branch).
   - Matrix: `os: [windows-latest, macos-latest, ubuntu-latest]`.
   - Install Python (e.g. 3.10, 3.11, 3.12; one version per OS or matrix).
   - `pip install -e .` and optional deps: `pip install xxhash send2trash`.
   - `python -m pytest dedup/tests -v --tb=short`.
   - Optional: upload test results / coverage artifact.

2. Ensure tests are deterministic and path-agnostic (temp_dir already used; no hardcoded /tmp or C:\).

3. Add a “CI” badge to README linking to the workflow run page.

**Acceptance:**  
- Workflow green on all three OSes for current test suite.
- README updated with badge (optional).

---

## Suggested order of implementation

| Order | Item    | Effort  | Impact                          |
|-------|---------|---------|----------------------------------|
| 1     | 5.3 CI  | Small   | Prevents regressions on all OSes |
| 2     | 5.2a Pagination | Small | Large result sets usable        |
| 3     | 5.1b Streaming/temp DB | Large | Bounded memory for huge scans   |
| 4     | 5.2b/c Virtual list | Medium | Only if 5.2a insufficient       |

---

## Out of scope for Phase 5

- Visual/fuzzy matching, cloud storage, real-time monitoring (per IMPLEMENTATION_SUMMARY).
- New UI framework or breaking engine API changes.
