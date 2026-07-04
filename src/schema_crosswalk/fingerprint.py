"""Fingerprint + schema-drift differ. [PURE]

The fingerprint is a shape-only SHA-256 (sorted paths + types + nullability); it contains no
cell values and is safe to log/store (design.md 8.2). Drift detection compares a new profile
against a prior approved one and emits a delta (design.md 8.4).
"""

from __future__ import annotations

from .models import DriftReport, SourceProfile


def compute_fingerprint(profile: SourceProfile) -> str:
    """Return ``"sha256:<hex>"`` over the canonical, value-free shape of the profile."""
    raise NotImplementedError


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
    raise NotImplementedError
