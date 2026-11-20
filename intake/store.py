import json
import sqlite3
from dataclasses import dataclass

from intake.quality import QualityWindow, classify_window
from intake.segments import AffineSegment


@dataclass(frozen=True)
class StoredRecording:
    station_id: str
    recording_id: str
    windows: tuple[QualityWindow, ...]
    segments: tuple[AffineSegment, ...]


class RecordingStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                station_id TEXT NOT NULL,
                recording_id TEXT NOT NULL,
                windows_json TEXT NOT NULL,
                segments_json TEXT NOT NULL,
                PRIMARY KEY (station_id, recording_id)
            )
        ''')

    def save_batch(self, batch: StoredRecording) -> None:
        windows = json.dumps([window.as_row() for window in batch.windows])
        segments = json.dumps([segment.as_row() for segment in batch.segments])
        with self.db:
            self.db.execute(
                'INSERT INTO recordings VALUES (?, ?, ?, ?)',
                (batch.station_id, batch.recording_id, windows, segments),
            )

    def load_batch(self, station_id: str, recording_id: str) -> StoredRecording:
        row = self.db.execute('''
            SELECT windows_json, segments_json FROM recordings
            WHERE station_id = ? AND recording_id = ?
        ''', (station_id, recording_id)).fetchone()
        if row is None:
            raise KeyError(f'unknown recording: {station_id}/{recording_id}')
        windows_json, segments_json = row
        return StoredRecording(
            station_id, recording_id,
            tuple(classify_window(window) for window in json.loads(windows_json)),
            tuple(AffineSegment(**segment) for segment in json.loads(segments_json)),
        )
