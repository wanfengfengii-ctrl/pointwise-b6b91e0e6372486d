import sqlite3
from collections.abc import Iterable, Mapping

from exact import required_text
from intake.calibration import CalibrationRegistry
from intake.quality import classify_window
from intake.segments import build_valid_segments, validate_nonconflicting_windows
from intake.store import RecordingStore, StoredRecording


def record(
    db: sqlite3.Connection, station_id: str, recording_id: str, rows: Iterable[Mapping]
) -> StoredRecording:
    required_text(station_id, 'station_id')
    required_text(recording_id, 'recording_id')
    if not isinstance(rows, Iterable):
        raise ValueError('recording rows must be iterable')
    windows = tuple(sorted((classify_window(row) for row in rows), key=lambda row: row.start))
    validate_nonconflicting_windows(windows)
    registry = CalibrationRegistry(db)
    references = dict.fromkeys(
        window.calibration_id for window in windows if window.calibration_id is not None
    )
    calibrations = {reference: registry.resolve(reference) for reference in references}
    batch = StoredRecording(station_id, recording_id, windows, build_valid_segments(windows, calibrations))
    RecordingStore(db).save_batch(batch)
    return batch


def read_recording(db: sqlite3.Connection, station_id: str, recording_id: str) -> StoredRecording:
    return RecordingStore(db).load_batch(station_id, recording_id)
