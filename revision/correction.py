from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from exact import rational, required_text
from intake.segments import AffineSegment, validate_segment_order

if TYPE_CHECKING:
    from revision.snapshots import FrozenRevision


@dataclass(frozen=True)
class Correction:
    start: Fraction
    end: Fraction
    segments: tuple[AffineSegment, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, 'start', rational(self.start, 'correction start'))
        object.__setattr__(self, 'end', rational(self.end, 'correction end'))
        required_text(self.reason, 'correction reason')
        if self.start >= self.end:
            raise ValueError('correction window must have positive duration')
        if not isinstance(self.segments, (tuple, list)):
            raise ValueError('correction segments must be a tuple or list')
        if any(not isinstance(segment, AffineSegment) for segment in self.segments):
            raise ValueError('correction segments must be calibrated affine segments')
        replacements = tuple(sorted(self.segments, key=lambda segment: segment.start))
        validate_segment_order(replacements)
        if any(segment.start < self.start or segment.end > self.end for segment in replacements):
            raise ValueError('replacement exceeds its correction window')
        object.__setattr__(self, 'segments', replacements)


def apply_correction(parent: FrozenRevision, correction: Correction) -> tuple[AffineSegment, ...]:
    combined = list(correction.segments)
    for segment in parent.segments:
        if segment.end <= correction.start or segment.start >= correction.end:
            combined.append(segment)
            continue
        if segment.start < correction.start:
            combined.append(segment.clip(segment.start, correction.start))
        if segment.end > correction.end:
            combined.append(segment.clip(correction.end, segment.end))
    combined.sort(key=lambda segment: segment.start)
    validate_segment_order(combined)
    return tuple(combined)
