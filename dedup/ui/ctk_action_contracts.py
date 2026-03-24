"""
Shared CTK action contracts.

Keeps payload keys and callback signatures centralized while pages migrate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

ScanMode = Literal["photos", "videos", "files"]
PostScanRoute = Literal["review", "scan", "mission"]
KeepPolicy = Literal["newest", "oldest", "largest", "smallest", "first"]


class ScanStartPayload(TypedDict):
    mode: ScanMode
    path: str
    options: dict
    keep_policy: KeepPolicy
    post_scan_route: PostScanRoute


@dataclass(frozen=True)
class CtkOwnershipRule:
    feature: str
    primary_owner: str
    allowed_secondary: tuple[str, ...] = ()
