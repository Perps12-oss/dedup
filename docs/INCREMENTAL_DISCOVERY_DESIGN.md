# Cross-Session Incremental Discovery Design

**Goal:** Allow a brand-new scan (new `session_id`) to reuse prior inventory safely instead of rediscovering everything from scratch.

**Status:** Design proposal – not implemented.

---

## 1. Problem

Today, inventory and hash artifacts are **session-scoped**. A new scan always:
1. Creates a fresh `session_id`
2. Walks the full filesystem
3. Writes a fresh inventory

Prior completed sessions' inventory is never consulted. On large trees (100k+ files, especially on OneDrive/network drives), discovery dominates runtime.

---

## 2. Compatibility Criteria (When Can We Reuse?)

A prior session is eligible for inventory reuse only if:

| Criterion | Rationale |
|-----------|-----------|
| Same roots | `root_fingerprint` match – we're scanning the same directories |
| Same discovery config | `min_size_bytes`, `allowed_extensions`, `exclude_dirs`, `include_hidden`, etc. – or we'd get wrong file set |
| Discovery phase completed | Prior session has a finalized discovery checkpoint |
| Same schema version | Avoid version skew |

**Proposal:** Add `discovery_config_hash` (roots + discovery filters) separate from full `config_hash`. Reuse when `discovery_config_hash` matches. If user changed hash strategy but not discovery options, we still reuse inventory.

---

## 3. Two Approaches

### Approach A: Full Walk + Prior Merge (simpler, less I/O gain)

**Idea:** Load prior inventory for compatible session. Walk full tree as today. Merge: add new, update modified, drop deleted. Write merged inventory to new session.

**Pros:**
- No schema change if we only use prior as "hint" for unchanged files
- Logic is straightforward: walk produces truth; prior is optional optimization
- Safe: we always verify against filesystem

**Cons:**
- We still do a full `os.scandir` + `stat()` for every file → no I/O savings
- Real win is only in *later phases* (fewer hash lookups if path+size+mtime match and hash cache hits)
- Discovery time barely improves

**Conclusion:** Not worth it for discovery speed. Only useful if we want to show "reused N files from prior scan" in UI.

---

### Approach B: Directory-Level Mtime Skip (true incremental, big I/O gain) ✅

**Idea:** Store directory metadata (path + mtime) from each run. When discovering, for each directory:

1. `stat()` the directory first
2. If we have prior inventory for this dir **and** dir mtime unchanged → **skip recursion**, reuse prior file list for that subtree
3. Else → recurse as today, discover

**I/O savings:** Unchanged subtrees (e.g. 90% of a photo library) require one `stat()` per directory instead of full tree walk. Large win on slow/network drives.

**Requirements:**
- Prior session must have recorded **directory path + mtime** (or equivalent: ctime, or a digest of child names)
- New schema/table or extension to persist this
- Discovery logic must branch: check dir mtime before recursing

---

## 4. Storage Model

### Option B1: Directory manifest table (new)

```
CREATE TABLE discovery_dir_manifest (
    session_id TEXT NOT NULL,
    dir_path TEXT NOT NULL,
    dir_mtime_ns INTEGER NOT NULL,
    file_count INTEGER NOT NULL,
    PRIMARY KEY (session_id, dir_path),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);
```

- Populated at end of discovery: for each directory we scanned, store `(dir_path, dir_mtime_ns, file_count)`.
- On incremental: query prior session for `dir_path` → if current `stat().st_mtime_ns == dir_mtime_ns`, skip recursion and load prior file list for that dir.

**Problem:** We don't currently store "which dir each file came from" in a cheap way. We can derive it: `dir_path = os.path.dirname(file.path)`. Prior inventory grouped by dir gives us the file list. So we'd add a `dir_manifest` that maps `dir_path → mtime_ns` for skip decision, and use `inventory_files` grouped by dir for the file list when we skip.

**Simpler variant:** Store only `(session_id, dir_path, dir_mtime_ns)`. When we skip a dir, we must have prior files for that dir. Query: `SELECT path, size_bytes, mtime_ns, inode FROM inventory_files WHERE session_id=? AND path LIKE dir_path || '/%'` (or `path GLOB dir_path || '/*'`). That works but can be slow for many dirs. Better: maintain `parent_dir` or `dir_path` column in inventory, or a separate `inventory_dirs` index.

**Better structure:**

```
-- Maps dir → mtime at discovery time. Used to decide "skip this dir or not?"
CREATE TABLE discovery_dir_mtimes (
    session_id TEXT NOT NULL,
    dir_path TEXT NOT NULL,
    dir_mtime_ns INTEGER NOT NULL,
    PRIMARY KEY (session_id, dir_path)
);

-- Optional: index to quickly get files per dir (avoid full scan)
CREATE INDEX idx_inventory_parent_dir ON inventory_files(session_id, parent_dir);
```

Add `parent_dir TEXT` to `inventory_files` (or derive from `path` – `parent_dir = path[:path.rfind('/')]` or use `os.path.dirname`). When we skip a dir, we need fast "give me all files under this dir from prior session". Index on `(session_id, parent_dir)` makes that cheap.

**Minimal change:** Don't add `parent_dir`. When skipping dir D, query:
```sql
SELECT path, size_bytes, mtime_ns, inode FROM inventory_files
WHERE session_id = ? AND (
    path = ?  -- dir itself as file (unlikely)
    OR path LIKE ? || '/%'   -- descendants
);
```
`?` = prior session id, dir path. SQLite `LIKE` with leading constant is indexable if we have `path` index. We have `UNIQUE(session_id, path)`. A `CREATE INDEX idx_inventory_session_path_prefix ON inventory_files(session_id, path)` could help prefix lookups.

---

## 5. Algorithm (Approach B)

### 5.1 Prior-session selection

```python
def find_compatible_prior_session(
    persistence,
    roots: List[Path],
    discovery_config: dict,
) -> Optional[str]:
    """Return session_id of most recent completed session with same roots + discovery config."""
    root_fp = _root_fingerprint(roots)
    disc_hash = _discovery_config_hash(discovery_config)
    for session_id in persistence.list_sessions_by_root_fingerprint(root_fp):
        s = persistence.session_repo.get(session_id)
        if s.get("status") != "completed":
            continue
        if s.get("discovery_config_hash") != disc_hash:
            continue
        if not is_phase_complete(session_id, ScanPhase.DISCOVERY):
            continue
        return session_id
    return None
```

### 5.2 Discovery loop change

**Current:** `_scan_directory(d)` → scandir(d), for each file stat+emit, for each subdir put on work queue.

**Incremental:**
```python
def _scan_directory(self, directory, work_queue, result_queue):
    if self._prior_session_id and self._dir_mtimes is not None:
        prior_mtime = self._dir_mtimes.get(str(directory))
        try:
            curr_stat = directory.stat()
            curr_mtime_ns = getattr(curr_stat, 'st_mtime_ns', int(curr_stat.st_mtime * 1e9))
            if prior_mtime == curr_mtime_ns:
                # Skip recursion - emit prior files for this dir and its subdirs
                for meta in self._emit_prior_files_for_tree(directory):
                    result_queue.put(meta)
                return
        except OSError:
            pass  # Fall back to full scan

    # Full scan path (existing logic)
    with os.scandir(str(directory)) as entries:
        for entry in entries:
            ...
```

`_emit_prior_files_for_tree(dir)` loads from prior session all files under `dir` (recursively). We can do this by:
- Querying inventory where `path LIKE dir || '/%'` or `path = dir` (for the dir itself as file)
- Or storing a mapping `dir → [file_ids]` during prior run (denormalized but fast)

**Subdir handling:** When we skip a dir, we also skip recursing into its subdirs. So we need prior files for the entire subtree. Query: `path LIKE dir || '/%'` covers all descendants. Emit those as FileMetadata. No need to recurse.

### 5.3 Recording dir mtimes at end of discovery

When we finish a full scan, we have scanned a set of directories. We need to record `(dir_path, dir_mtime_ns)` for each. During `_scan_directory` we already visit each dir. We can:
- Maintain a `dict[Path, int]` of `dir -> mtime_ns` as we go
- At end of discovery, batch-insert into `discovery_dir_mtimes`

For directories we *skip* (incremental), we don't have their mtime from this run – we use the prior run's mtime as the "last known" value. When we skip, we've verified current mtime matches that, so we're good.

---

## 6. Safety and Correctness

| Risk | Mitigation |
|------|-------------|
| Dir mtime not updated on child change | Some filesystems don't update parent mtime when file changes. Use `ctime` or child checksum as fallback for paranoid mode; default to mtime (Linux/macOS/Windows generally update it). |
| Clock skew / mtime granularity | Use `st_mtime_ns` when available; same precision in prior and current. |
| Prior session from different machine | `root_fingerprint` includes root paths. If paths differ (e.g. `C:\` vs `D:\`), no reuse. If same path, OK. |
| Config drift | Strict `discovery_config_hash` match. If user changes min_size or excludes, no reuse. |
| Reuse of deleted session's inventory | Only use sessions that exist and have completed discovery. `list_sessions_by_root_fingerprint` filters. |
| Partial/corrupt prior state | Validate prior: dir_mtimes count, inventory count. If inconsistent, fall back to full scan. |

---

## 7. Config and Feature Flag

```python
# ScanConfig
incremental_discovery: bool = True   # Use prior inventory when compatible
incremental_discovery_max_age_days: Optional[int] = 30  # Ignore prior older than N days (optional)
```

If `incremental_discovery=False`, always do full discovery (current behavior).

---

## 8. Migration Path

1. **Phase 1 (no schema change):** Add `find_compatible_prior_session` and `discovery_config_hash`. When starting discovery, if prior exists, load its inventory into memory. Run full walk, merge. Write merged to new session. **No I/O savings**, but validates prior-selection logic and merge behavior.

2. **Phase 2 (schema + dir mtime skip):**
   - Add migration: `discovery_dir_mtimes` table.
   - Add `discovery_config_hash` to `scan_sessions`.
   - During discovery: record dir mtimes as we scan.
   - In incremental mode: check dir mtime before recursing; skip and emit prior files when unchanged.
   - Add `parent_dir` or use `path LIKE` for subtree queries.

3. **Phase 3 (optional):** Optimize subtree query (e.g. `parent_dir` column, covering index). Tune batch sizes for prior-file emission.

---

## 9. Hash Phase Reuse

Discovery reuse does **not** automatically reuse partial/full hashes. Those are keyed by `(session_id, file_id)`. File IDs are different in the new session.

We already have a **global hash cache** (path + size + mtime → hash). When we reuse prior inventory for a file, we insert it into the new session with a new file_id. Later, when hashing, the hash cache will hit if path+size+mtime match. So full-hash phase gets cache hits without further work.

For **partial hashes**, the cache key might differ. If the hash cache includes partial hash and uses path+size+mtime, we'd get hits. Need to verify `hash_cache` schema and usage. If not, we could add a "seed partial hash from prior session" step when path+size+mtime match – more complex, can be Phase 3+.

---

## 10. Summary

| Component | Change |
|-----------|--------|
| **Compatibility** | `discovery_config_hash` in session; `find_compatible_prior_session()` |
| **Schema** | `discovery_dir_mtimes(session_id, dir_path, dir_mtime_ns)`; optional `parent_dir` on inventory |
| **Discovery** | Check dir mtime before recursing; skip subtree and emit prior files when unchanged |
| **Recording** | Persist dir mtimes at end of discovery |
| **Config** | `incremental_discovery: bool`, optionally `incremental_discovery_max_age_days` |
| **Fallback** | Any error or mismatch → full scan (current behavior) |

**Recommended implementation order:** Phase 1 (prior merge, full walk) to validate plumbing, then Phase 2 (dir mtime skip) for real I/O gains.
