# Review scale-out (Phase 3B)

Bounded behavior so the Review page stays usable with large duplicate sets.

## Navigator

- **Max visible rows:** The Group Navigator shows at most `REVIEW_NAVIGATOR_MAX_ROWS` (2000) rows. If there are more groups, the label shows "Showing first N of M groups". All groups still contribute to the deletion plan (delete count, reclaimable); only the list is capped to keep the Treeview from growing unbounded.
- **Future:** Paged "Load more" or virtualized scrolling can be added later without changing the cap; the cap is the first line of defense.

## Thumbnails

- Thumbnails are loaded per group when the user selects that group (Gallery/Compare). We do not materialize thumbnails for all groups up front.
- `generate_thumbnails_async` is used so the UI stays responsive; the cache is bounded by the thumbnail cache dir and eviction policy.

## Preview / execute

- Plan is built from the full VM (all groups and keep selections). The navigator cap does not limit how many files can be included in the deletion plan; it only limits how many rows are drawn in the list.

## Scale-aware UX (3B.2)

- **Navigator:** Fixed table height (16 rows) and vertical scroll; only the first `REVIEW_NAVIGATOR_MAX_ROWS` rows are created, so scroll and selection stay stable with large datasets.
- **Workspace:** One group is loaded at a time (Table/Gallery/Compare); no progressive loading of all groups. Thumbnails load on demand for the selected group.
- **Right rail:** Plan summary and readiness line update from VM; no extra network or heavy work on redraw.
