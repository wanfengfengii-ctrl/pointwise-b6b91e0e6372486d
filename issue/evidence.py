from dataclasses import dataclass
from fractions import Fraction

from revision.snapshots import FrozenRevision


@dataclass(frozen=True)
class FrozenEvidence:
    affine_rows: tuple[tuple[Fraction, Fraction, Fraction, Fraction], ...]

    def to_body(self) -> dict[str, list[list[str]]]:
        return {'affine': [[str(value) for value in row] for row in self.affine_rows]}


def freeze_evidence(revision: FrozenRevision) -> FrozenEvidence:
    rows = []
    for segment in revision.segments:
        slope = (segment.temperature_end - segment.temperature_start) / (segment.end - segment.start)
        intercept = segment.temperature_start - slope * segment.start
        rows.append((segment.start, segment.end, slope, intercept))
    return FrozenEvidence(tuple(rows))
