import json
import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from intake.segments import AffineSegment, validate_segment_order
from revision.correction import Correction
from revision.lineage import RevisionOrigin


@dataclass(frozen=True)
class FrozenRevision:
    revision_id: str
    origin: RevisionOrigin
    segments: tuple[AffineSegment, ...]
    correction: Correction | None


def _encode_correction(correction: Correction | None) -> str | None:
    if correction is None:
        return None
    return json.dumps({
        'start': str(correction.start),
        'end': str(correction.end),
        'reason': correction.reason,
        'segments': [segment.as_row() for segment in correction.segments],
    })


def _restore_revision(row: tuple) -> FrozenRevision:
    revision_id, station_id, recording_id, parent_id, segments_json, correction_json = row
    segments = tuple(AffineSegment(**value) for value in json.loads(segments_json))
    correction = None
    if correction_json is not None:
        data = json.loads(correction_json)
        data['segments'] = tuple(AffineSegment(**value) for value in data['segments'])
        correction = Correction(**data)
    return FrozenRevision(revision_id, RevisionOrigin(station_id, recording_id, parent_id), segments, correction)


class SnapshotStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS revisions (
                revision_id TEXT PRIMARY KEY NOT NULL,
                station_id TEXT NOT NULL,
                recording_id TEXT NOT NULL,
                parent_revision_id TEXT REFERENCES revisions(revision_id),
                segments_json TEXT NOT NULL,
                correction_json TEXT,
                CHECK ((parent_revision_id IS NULL) = (correction_json IS NULL))
            )
        ''')

    def insert(
        self, origin: RevisionOrigin, segments: tuple[AffineSegment, ...], correction: Correction | None = None
    ) -> FrozenRevision:
        validate_segment_order(segments)
        if (origin.parent_revision_id is None) != (correction is None):
            raise ValueError('only child revisions carry a correction')
        revision = FrozenRevision(f'rev-{uuid4().hex}', origin, tuple(segments), correction)
        segments_json = json.dumps([segment.as_row() for segment in revision.segments])
        with self.db:
            self.db.execute('''
                INSERT INTO revisions (
                    revision_id, station_id, recording_id, parent_revision_id, segments_json, correction_json
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                revision.revision_id, origin.station_id, origin.recording_id,
                origin.parent_revision_id, segments_json, _encode_correction(correction),
            ))
        return revision

    def get(self, station_id: str, revision_id: str) -> FrozenRevision:
        row = self.db.execute('''
            SELECT revision_id, station_id, recording_id, parent_revision_id, segments_json, correction_json
            FROM revisions WHERE station_id = ? AND revision_id = ?
        ''', (station_id, revision_id)).fetchone()
        if row is None:
            raise KeyError(f'unknown revision: {station_id}/{revision_id}')
        return _restore_revision(row)

    def list_frozen(self, station_id: str) -> tuple[FrozenRevision, ...]:
        rows = self.db.execute('''
            SELECT revision_id, station_id, recording_id, parent_revision_id, segments_json, correction_json
            FROM revisions WHERE station_id = ? ORDER BY rowid
        ''', (station_id,))
        return tuple(_restore_revision(row) for row in rows)
