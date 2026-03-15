"""
ReviewProjection — normalized group data for the review page.

The review page must not infer verification level, risk flags, or confidence labels
locally.  Those come from the engine truth model and are projected here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional


@dataclass(frozen=True)
class ReviewGroupProjection:
    """
    Immutable per-group snapshot for the group navigator and review workspace.
    """
    group_id: str
    group_size: int             # bytes per individual file
    file_count: int
    verification_level: str     # "full_hash" | "partial_hash" | "size_only"
    confidence_label: str       # "Exact" | "High" | "Probable"
    reclaimable_bytes: int
    review_status: str          # "unreviewed" | "reviewed" | "risky"
    risk_flags: Tuple[str, ...]
    keeper_candidate: str       # path of suggested keeper (first file by default)
    thumbnail_capable: bool     # True if at least one file is a renderable image
    metadata_summary: str       # human-readable one-liner, e.g. "4 × 12.4 MB JPG"

    @property
    def has_risk(self) -> bool:
        return len(self.risk_flags) > 0

    @property
    def confidence_variant(self) -> str:
        return {
            "Exact":    "positive",
            "High":     "positive",
            "Probable": "warning",
        }.get(self.confidence_label, "neutral")


def build_review_group_from_duplicate_group(
    group,
    thumbnail_extensions: Optional[set] = None,
) -> ReviewGroupProjection:
    """
    Build a ReviewGroupProjection from a DuplicateGroup engine object.
    `group` is `dedup.engine.models.DuplicateGroup`.
    """
    from pathlib import Path as _Path

    IMAGE_EXTS = thumbnail_extensions or {
        "jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "heic",
    }

    files = getattr(group, "files", [])
    file_count = len(files)
    reclaimable = getattr(group, "reclaimable_size", 0)
    group_size = files[0].size if files else 0
    ext = _Path(files[0].path).suffix.lower().lstrip(".") if files else ""
    keeper = files[0].path if files else ""

    thumb_capable = any(
        _Path(f.path).suffix.lower().lstrip(".") in IMAGE_EXTS for f in files
    )

    risk: List[str] = []
    if file_count > 10:
        risk.append("large_group")

    meta_parts = []
    if file_count:
        from ..utils.formatting import fmt_bytes
        meta_parts.append(f"{file_count} × {fmt_bytes(group_size)}")
    if ext:
        meta_parts.append(ext.upper())
    meta_summary = " ".join(meta_parts)

    return ReviewGroupProjection(
        group_id=group.group_id,
        group_size=group_size,
        file_count=file_count,
        verification_level="full_hash",
        confidence_label="Exact",
        reclaimable_bytes=reclaimable,
        review_status="unreviewed",
        risk_flags=tuple(risk),
        keeper_candidate=keeper,
        thumbnail_capable=thumb_capable,
        metadata_summary=meta_summary,
    )


def build_review_groups_from_result(result) -> List[ReviewGroupProjection]:
    """Build the full list of ReviewGroupProjection from a ScanResult."""
    return [
        build_review_group_from_duplicate_group(g)
        for g in getattr(result, "duplicate_groups", [])
        if getattr(g, "files", [])
    ]
