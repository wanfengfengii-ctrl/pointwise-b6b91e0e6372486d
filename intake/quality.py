from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from exact import rational, required_text


class QualityMark(str, Enum):
    VALID = 'valid'
    MISSING = 'missing'


@dataclass(frozen=True)
class QualityWindow:
    start: Fraction
    end: Fraction
    quality: QualityMark
    calibration_id: str | None
    raw_start: Fraction | None
    raw_end: Fraction | None

    def as_row(self) -> dict:
        return {
            'start': str(self.start),
            'end': str(self.end),
            'quality': self.quality.value,
            'calibration_id': self.calibration_id,
            'raw_start': None if self.raw_start is None else str(self.raw_start),
            'raw_end': None if self.raw_end is None else str(self.raw_end),
        }


def classify_window(row: Mapping) -> QualityWindow:
    fields = {'start', 'end', 'quality', 'calibration_id', 'raw_start', 'raw_end'}
    if not isinstance(row, Mapping) or row.keys() - fields:
        raise ValueError('invalid recording row')
    start = rational(row.get('start'), 'start')
    end = rational(row.get('end'), 'end')
    if start >= end:
        raise ValueError('recording window must have positive duration')
    quality = QualityMark(row.get('quality'))
    calibration_id = row.get('calibration_id')
    if calibration_id is not None:
        required_text(calibration_id, 'calibration_id')
    raw_start, raw_end = row.get('raw_start'), row.get('raw_end')
    if quality is QualityMark.MISSING:
        if raw_start is not None or raw_end is not None:
            raise ValueError('missing windows cannot carry readings')
        return QualityWindow(start, end, quality, calibration_id, None, None)
    required_text(calibration_id, 'calibration_id')
    return QualityWindow(
        start, end, quality, calibration_id,
        rational(raw_start, 'raw_start'), rational(raw_end, 'raw_end'),
    )
