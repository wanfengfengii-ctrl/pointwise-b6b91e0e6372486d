import sqlite3

from intake.recording import read_recording
from revision.catalog import select_frozen_revision
from revision.correction import Correction, apply_correction
from revision.lineage import child_origin, initial_origin
from revision.snapshots import FrozenRevision, SnapshotStore


def freeze(
    db: sqlite3.Connection,
    station_id: str,
    *,
    recording_id: str | None = None,
    parent_revision_id: str | None = None,
    correction: Correction | None = None,
) -> FrozenRevision:
    store = SnapshotStore(db)
    if parent_revision_id is None:
        if recording_id is None or correction is not None:
            raise ValueError('an initial freeze requires a recording and no correction')
        origin = initial_origin(station_id, recording_id)
        batch = read_recording(db, station_id, recording_id)
        return store.insert(origin, batch.segments)
    if not isinstance(correction, Correction):
        raise ValueError('a child freeze requires a correction')
    parent = select_frozen_revision(db, station_id, parent_revision_id)
    origin = child_origin(parent.origin, parent.revision_id, station_id, recording_id)
    return store.insert(origin, apply_correction(parent, correction), correction)
