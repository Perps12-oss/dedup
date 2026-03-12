# DEDUP – TO DO & Enhancements

Source: [TO DO -ENHANCEMENTS](https://github.com/Perps12-oss/dedup/blob/main/TO%20DO%20-ENHANCEMENTS) in the repo. This file captures the reference implementation sketch and the suggested architectural and UX enhancements for the DEDUP engine and UI.

---

## Reference: FastDedupEngine sketch

Configuration and structure from the reference design (for alignment; current DEDUP uses `dedup/engine/` pipeline):

```python
# --- CONFIGURATION ---
PARTIAL_HASH_SIZE = 8192  # 8KB
FULL_HASH_CHUNK = 1024 * 1024  # 1MB
MAX_IO_THREADS = 32  # High thread count for I/O queue depth
DB_BATCH_SIZE = 10000  # SQLite write batch size
```

- **Phase 1:** Fast size discovery → write path/size to temp DB; filter to sizes with duplicates.
- **Phase 2:** Concurrent partial hashing (first N bytes) → index by partial_hash; filter to size+partial duplicates.
- **Phase 3:** Concurrent full hashing → index by full_hash; extract duplicate groups.

Current DEDUP already uses: size → partial hash (first+middle+last) → full hash; SQLite persistence and hash cache; batched processing. The sketch suggests PRAGMAs (WAL, batch size), iterative traversal, and batched executor submission as enhancements.

---

## 1. Critical architectural enhancements (engine)

### 1.1 Inode and hardlink awareness (safety)

- **Issue:** Two paths can be hardlinks to the same data. Hashing both and treating them as “duplicates” is misleading; deleting one does not free space.
- **Enhancement:** In Phase 1 (discovery), record `st_dev` and `st_ino`. If two files share (device, inode), treat as hardlinks: group them once and do not hash twice; in UI, show as “hardlinked” and do not count reclaimable space for deleting one.

### 1.2 Iterative directory traversal (stability)

- **Issue:** Deep trees (e.g. deep `node_modules`) can cause `RecursionError` with recursive `scan_dir`.
- **Enhancement:** Replace recursion with an iterative stack or queue (e.g. `collections.deque`). Bounded memory and no recursion limit.

### 1.3 Batched thread submission (memory safety)

- **Issue:** Submitting one future per path (e.g. 500k paths) allocates 500k futures up front.
- **Enhancement:** Feed paths to the executor in batches (e.g. 5k at a time); submit the next batch as the previous completes. Keeps memory flat for 10k or 10M files.

### 1.4 Disk/media-aware concurrency

- **Issue:** `MAX_IO_THREADS = 32` can thrash HDDs; SSDs benefit from higher queue depth.
- **Enhancement:** Detect or configure drive type (SSD vs HDD) or scale by mount point. Use fewer threads (1–4) for HDDs and more (16–32) for SSDs.

### 1.5 Memory-mapped I/O (mmap) for very large files

- **Issue:** For very large files (e.g. 50GB), sequential Python read loops add overhead.
- **Enhancement:** For files above a threshold (e.g. >500MB), use `mmap` and feed the mapping to the hash function so the OS handles paging; can improve throughput for huge files.

### 1.6 Event/telemetry hooks (UI responsiveness)

- **Issue:** Long Phase 2/3 runs make the UI look frozen.
- **Enhancement:** Add an event bus or callbacks (e.g. `on_progress(phase, current, total)`) and emit progress every `DB_BATCH_SIZE` or at a throttled interval so the UI stays responsive.

---

## 2. Post-scan review: action and implementation plan

### Phase 1: Action plan (features & UX)

| # | Action | Description |
|---|--------|-------------|
| 2.1 | **Data enrichment & categorization** | Group duplicates by file type (Images, Videos, Documents, Archives, Audio, Others). Enrich with metadata: date created/modified, resolution (images), folder. |
| 2.2 | **Visual “side-by-side” grouping** | Show duplicates in clearly separated groups (e.g. alternating background). For image groups, show a grid of thumbnails next to metadata so users can confirm identity. |
| 2.3 | **Smart selection assistants** | One-click rules: Keep Newest / Keep Oldest; Keep Shortest Path / Keep Deepest Path; “Select all in [folder/drive].” Ensure at least one file per group is never selected for deletion. |
| 2.4 | **Safety-net deletion queue** | On “Delete”, do not delete immediately: move to OS Recycle Bin/Trash or to a staging folder first. |

### Phase 2: Implementation plan (architecture)

| Step | Component | How |
|------|-----------|-----|
| 2.5 | **Metadata & thumbnail worker** | After the engine returns duplicate groups, pass them to a background worker. Worker categorizes by extension; for images, use Pillow to generate small thumbnails (e.g. 150×150) into a temp/cache dir. UI shows list immediately and lazy-loads thumbnails. |
| 2.6 | **UI state management** | View model per file: e.g. `is_selected`. Smart-selection actions (e.g. “Keep Newest”) update the model (e.g. set `is_selected` on older files) and trigger re-render. |
| 2.7 | **Results layout** | Split pane: left/top = category filters (Images (450), Documents (12), …) and smart-selection buttons; main area = scrollable list of groups. For images, use Canvas or scrollable Frame with Labels for thumbnails. |
| 2.8 | **Deletion pipeline** | DeletionManager: collect paths where `is_selected == True`, pass to send2trash (or staging); show progress while moving. |

---

## 3. Mapping to current DEDUP

| Enhancement | Current DEDUP | Next step |
|-------------|----------------|-----------|
| Hardlink awareness | Discovery has `inode` in `FileMetadata` | Group by (dev, inode) in discovery/grouping; exclude “duplicate” hardlinks from reclaimable. |
| Iterative traversal | Discovery uses a queue and workers | Already iterative; verify no recursion in hot path. |
| Batched executor | Grouping/hashing process in batches | Confirm executor receives work in batches, not all-at-once. |
| Disk-aware threads | `max_workers` is fixed | Add optional config or detection (SSD vs HDD) and scale workers. |
| mmap for large files | Hashing uses chunked read / mmap for large | Check hashing module for mmap path and threshold. |
| Progress hooks | Pipeline has `progress_cb`; UI uses it | Ensure callbacks are throttled and show phase/current/total. |
| Category grouping | `media_types.py` + Results by group | Add “filter by category” in Results (Images, Documents, …). |
| Thumbnails | `thumbnails.py` + Results strip | Already in place; align with “grid per group” if desired. |
| Smart selection | “Keep this file” per group | Add “Keep Newest/Oldest”, “Keep Shortest/Deepest path”. |
| Safety net | Trash by default; staging optional | Already trash-first; document or add “staging folder” option. |

---

## 4. References

- Repo file: [TO DO -ENHANCEMENTS](https://github.com/Perps12-oss/dedup/blob/main/TO%20DO%20-ENHANCEMENTS)
- Internal plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- Audit and current status: [AUDIT_SUMMARY.md](AUDIT_SUMMARY.md)
