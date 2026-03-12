# DEDUP Implementation, Enhance & Refactor Plan

This plan is derived from **IMPLEMENTATION_SUMMARY.md** and the current codebase. It prioritizes work that aligns with the doc’s architecture, testing, and performance goals without expanding scope (e.g. no visual/fuzzy/cloud features).

**See also:** [TODO-ENHANCEMENTS.md](TODO-ENHANCEMENTS.md) — content from the repo’s [TO DO -ENHANCEMENTS](https://github.com/Perps12-oss/dedup/blob/main/TO%20DO%20-ENHANCEMENTS) file: FastDedupEngine sketch, six critical engine enhancements (hardlinks, iterative traversal, batched threads, disk-aware concurrency, mmap, progress hooks), and the post-scan review action/implementation plan (categories, thumbnails, smart selection, safety net).

---

## Phase 1: Align Documentation & Config (Low Risk)

| # | Task | Source | Action |
|---|------|--------|--------|
| 1.1 | Update directory structure in IMPLEMENTATION_SUMMARY | § Directory Structure | Add `media_types.py`, `thumbnails.py`, `trash.py`; use `__main__.py`; list `tests/` and new engine/infra modules. |
| 1.2 | Unify persistence path with summary | § Build and Run, coordinator | Coordinator currently uses a fixed path (`~/.local/share/dedup`). Use `get_default_persistence()` (platform-specific: Windows AppData, macOS Library, Linux .local) so behavior matches doc and AUDIT. |
| 1.3 | Document current vs “future” features | § Future Enhancements | In IMPLEMENTATION_SUMMARY, add a short “Implemented since summary” (checkpoint/resume, media filter, thumbnails, empty trash, history roots+resume) and point to AUDIT_SUMMARY §9. |

**Deliverables:** IMPLEMENTATION_SUMMARY.md updated; coordinator (or app bootstrap) uses default persistence when appropriate; no behavior change for engine.

---

## Phase 2: Testing (Per IMPLEMENTATION_SUMMARY § Testing Recommendations)

| # | Task | Source | Action |
|---|------|--------|--------|
| 2.1 | Unit tests per engine module | § Unit Tests | Add/expand: `test_grouping.py` (size/partial/full grouping, cancel); `test_pipeline.py` (run phases, cancel, checkpoint save/load); `test_deletion.py` (preview_deletion, empty_trash behavior if applicable). |
| 2.2 | Integration test: full pipeline | § Integration Tests | One test: synthetic directory → ScanPipeline.run() → assert duplicate_groups and reclaimable consistent with truthfulness rules. |
| 2.3 | Edge cases | § Edge Cases | Tests: empty directory; single file; symlinks (when follow_symlinks=True); permission-denied directory (discovery continues, no crash). |
| 2.4 | Performance / stress | § Performance Tests | Optional: script or pytest marker for “stress” run on 10k–50k files; assert completion and basic metrics; no hard 1M requirement in CI. |

**Deliverables:** New or extended tests under `dedup/tests/`; CI runs unit + integration; optional stress run documented.

---

## Phase 3: Refactors (From IMPLEMENTATION_SUMMARY Audit Table)

| # | Module | Audit action | Refactor |
|---|--------|--------------|----------|
| 3.1 | Worker | Simplified worker | Keep single ScanWorker; ensure all scan options (e.g. `allowed_extensions` from coordinator) are passed through; no extra worker types unless needed. |
| 3.2 | Config | Simplified configuration | Remove or narrow unused Config fields (e.g. `theme` if UI has no theme engine); keep defaults and validation. |
| 3.3 | Persistence / hash cache | Integrated into persistence | Already done; add a short integration test that re-scans same path and verifies cache hits (e.g. second run faster or hash_calls reduced). |
| 3.4 | Discovery | Streaming | Pipeline still does `list(discovery.discover())`. Option: use `discover_batch()` in pipeline and feed batches into grouping incrementally to cap memory per batch (larger refactor; document as “Phase 4 optional”). |

**Deliverables:** Config trimmed if safe; one cache-integration test; worker/config refactors minimal and backward compatible.

---

## Phase 4: Enhancements (Within Current Scope)

| # | Area | Enhancement | Notes |
|---|------|-------------|--------|
| 4.1 | Progress UI | ETA only when stable | Scan frame already avoids fake ETA; add “Estimating…” or show ETA only when `estimated_remaining_seconds` is set and throughput stable (reuse metrics_semantics helpers). |
| 4.2 | Progress UI | Throughput display | Show “files/s” or “MB/s” when available from ScanProgress; keep truthful (no fabricated rates). |
| 4.3 | Results UI | Large result sets | When duplicate_groups > N (e.g. 500), show summary first and lazy-load or paginate tree entries to keep UI responsive (optional; document as enhancement). |
| 4.4 | Coordinator | Scan options completeness | Ensure all ScanConfig fields used by the UI (e.g. `allowed_extensions` from media_category) are passed in `start_scan(**scan_options)` and that resume path does not drop options. |
| 4.5 | Thumbnails | Cache cleanup | Optional: add “Clear thumbnail cache” in settings or History/Results to avoid unbounded disk use. |

**Deliverables:** Progress UI improvements (4.1, 4.2); optional tree pagination and thumbnail cleanup documented or implemented.

---

## Phase 5: Optional / Later (Document Only Unless Prioritized)

| # | Item | Rationale |
|---|------|-----------|
| 5.1 | Streaming grouping | Pipeline currently materializes full file list; grouping then processes it. True streaming would feed batches from discovery → grouping and require grouping to accept iterators/batches; higher effort. |
| 5.2 | Results tree virtualization | For 100k+ groups, replace “load all into Treeview” with windowed/virtual list; depends on tkinter approach. |
| 5.3 | Cross-platform CI | § Cross-Platform: add GitHub Actions (or similar) for Windows, macOS, Linux to run unit + integration tests. |

---

## Suggested Order of Work

1. **Phase 1** – Update IMPLEMENTATION_SUMMARY and persistence path so the repo and docs match.
2. **Phase 2** – Add tests (grouping, pipeline, integration, edge cases) so refactors and enhancements are safe.
3. **Phase 3** – Small refactors (config, worker, cache test).
4. **Phase 4** – Progress and UX enhancements (ETA, throughput, optional pagination/cache cleanup).
5. **Phase 5** – Capture as “Future work” in README or IMPLEMENTATION_SUMMARY; implement when needed.

---

## Out of Scope (Per IMPLEMENTATION_SUMMARY)

- Visual similarity, fuzzy matching, cloud scanning, network optimizations, real-time monitoring, scheduled scans.
- No new UI framework or large rewrites; keep engine-first and truthful metrics.

---

## Summary Table

| Phase | Focus | Risk | Effort |
|-------|--------|------|--------|
| 1 | Docs + config/persistence alignment | Low | Small |
| 2 | Testing (unit, integration, edge) | Low | Medium |
| 3 | Refactors (config, worker, cache test) | Low | Small |
| 4 | Progress UI, throughput, optional UX | Low | Small–Medium |
| 5 | Streaming, virtualization, CI | Medium | Medium–High (optional) |

This plan implements and refactors the changes implied by IMPLEMENTATION_SUMMARY.md while keeping the project minimal and production-ready.
