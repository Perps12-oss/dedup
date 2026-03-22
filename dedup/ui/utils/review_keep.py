"""
Keep selection helpers for Decision Studio.

Invariant: each **duplicate group** (≥2 files) has **exactly one** protected path — the file
that will **not** be deleted for that group. Users may override Smart Select at any time;
Smart rules only **suggest** defaults. Invalid or missing entries are coerced to the first
file in the group (stable default).
"""

from __future__ import annotations

from typing import Any


def default_keep_map_from_result(result: Any) -> dict[str, str]:
    """One keeper per duplicate group: first file in each group with ≥2 members."""
    out: dict[str, str] = {}
    if not result or not getattr(result, "duplicate_groups", None):
        return out
    for group in result.duplicate_groups:
        files = list(getattr(group, "files", []) or [])
        if len(files) < 2:
            continue
        gid = str(getattr(group, "group_id", ""))
        out[gid] = files[0].path
    return out


def default_path_for_group(result: Any, group_id: str) -> str | None:
    """First file path for the given duplicate group, or None if not a multi-file group."""
    if not result or not getattr(result, "duplicate_groups", None):
        return None
    for group in result.duplicate_groups:
        if str(getattr(group, "group_id", "")) != group_id:
            continue
        files = list(getattr(group, "files", []) or [])
        if len(files) >= 2:
            return files[0].path
        return None
    return None


def coerce_keep_selections(result: Any, keep: dict[str, str] | None) -> dict[str, str]:
    """
    Ensure every duplicate group has a keeper path that is actually in that group.
    Missing or stale paths are replaced with the group's first file.
    """
    if not result or not getattr(result, "duplicate_groups", None):
        return dict(keep or {})
    out = dict(keep or {})
    for group in result.duplicate_groups:
        files = list(getattr(group, "files", []) or [])
        if len(files) < 2:
            continue
        path_set = {f.path for f in files}
        gid = str(getattr(group, "group_id", ""))
        cur = out.get(gid)
        if cur not in path_set:
            out[gid] = files[0].path
    return out
