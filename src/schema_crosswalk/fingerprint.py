"""Fingerprint + schema-drift differ. [PURE]

The fingerprint is a shape-only SHA-256 (sorted paths + types + nullability); it contains no
cell values and is safe to log/store (design.md 8.2). Drift detection compares a new profile
against a prior approved one and emits a delta (design.md 8.4).
"""

from __future__ import annotations

import hashlib
import json

from .models import DriftReport, SourceProfile


def compute_fingerprint(profile: SourceProfile) -> str:
    """Return ``"sha256:<hex>"`` over the canonical, value-free shape of the profile.

    Shape-only (design.md 8.2): sorted ``path`` + ``inferred_type`` + ``nullable``, with no
    cell values, so the digest is safe to log/store and is insensitive to row order/count.
    """
    shape = sorted(
        (
            {"path": f.path, "type": f.inferred_type.value, "nullable": f.nullable}
            for f in profile.fields
        ),
        key=lambda d: d["path"],
    )
    canonical = json.dumps(shape, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def diff_profiles(
    current: SourceProfile,
    prior: SourceProfile,
    *,
    prior_fingerprint: str,
) -> DriftReport:
    """Produce a :class:`DriftReport` describing how ``current`` drifted from ``prior``."""
    raise NotImplementedError


def field_overlap(a: SourceProfile, b: SourceProfile) -> float:
    """Jaccard overlap of field paths; used to find a drift neighbor (design.md 8.4)."""
    pa = {f.path for f in a.fields}
    pb = {f.path for f in b.fields}
    if not pa and not pb:
        return 1.0
    union = pa | pb
    return len(pa & pb) / len(union)
