import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from exact import RationalInput, rational, required_text


@dataclass(frozen=True)
class Calibration:
    calibration_id: str
    offset: Fraction


def apply_calibration(calibration: Calibration, reading: RationalInput) -> Fraction:
    return rational(reading, 'raw temperature') + calibration.offset


class CalibrationRegistry:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS calibrations (
                calibration_id TEXT PRIMARY KEY NOT NULL,
                offset TEXT NOT NULL
            )
        ''')

    def register(self, calibration_id: str, offset: RationalInput) -> Calibration:
        calibration = Calibration(
            required_text(calibration_id, 'calibration_id'), rational(offset, 'offset')
        )
        with self.db:
            self.db.execute(
                'INSERT INTO calibrations (calibration_id, offset) VALUES (?, ?)',
                (calibration.calibration_id, str(calibration.offset)),
            )
        return calibration

    def resolve(self, calibration_id: str) -> Calibration:
        required_text(calibration_id, 'calibration_id')
        row = self.db.execute(
            'SELECT offset FROM calibrations WHERE calibration_id = ?', (calibration_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f'unknown calibration: {calibration_id}')
        return Calibration(calibration_id, Fraction(row[0]))
