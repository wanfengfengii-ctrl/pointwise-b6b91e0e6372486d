from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from exact import rational
from intake.calibration import Calibration, apply_calibration
from intake.quality import QualityMark, QualityWindow


@dataclass(frozen=True)
class AffineSegment:
    start: Fraction
    end: Fraction
    temperature_start: Fraction
    temperature_end: Fraction

    def __post_init__(self) -> None:
        for name in ('start', 'end', 'temperature_start', 'temperature_end'):
            object.__setattr__(self, name, rational(getattr(self, name), name))
        if self.start >= self.end:
            raise ValueError('an affine segment must have positive duration')

    def temperature_at(self, time: Fraction) -> Fraction:
        if not self.start <= time <= self.end:
            raise ValueError('time is outside the affine segment')
        weight = (time - self.start) / (self.end - self.start)
        return self.temperature_start + weight * (self.temperature_end - self.temperature_start)

    def clip(self, start: Fraction, end: Fraction) -> 'AffineSegment':
        return AffineSegment(start, end, self.temperature_at(start), self.temperature_at(end))

    def as_row(self) -> dict[str, str]:
        return {
            'start': str(self.start),
            'end': str(self.end),
            'temperature_start': str(self.temperature_start),
            'temperature_end': str(self.temperature_end),
        }


def validate_nonconflicting_windows(windows: Sequence[QualityWindow]) -> None:
    for previous, current in zip(windows, windows[1:]):
        if previous.end > current.start:
            raise ValueError('recording windows overlap or are out of order')


def validate_segment_order(segments: Sequence[AffineSegment]) -> None:
    for previous, current in zip(segments, segments[1:]):
        if previous.end > current.start:
            raise ValueError('affine segments overlap or are out of order')


def build_valid_segments(
    windows: Sequence[QualityWindow], calibrations: Mapping[str, Calibration]
) -> tuple[AffineSegment, ...]:
    segments = []
    for window in windows:
        if window.quality is QualityMark.MISSING:
            continue
        calibration = calibrations[window.calibration_id]
        segments.append(AffineSegment(
            window.start,
            window.end,
            apply_calibration(calibration, window.raw_start),
            apply_calibration(calibration, window.raw_end),
        ))
    return tuple(segments)
