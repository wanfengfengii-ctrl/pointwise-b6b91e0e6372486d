import sqlite3

from exact import required_text
from revision.snapshots import FrozenRevision, SnapshotStore


def list_frozen_revisions(db: sqlite3.Connection, station_id: str) -> tuple[FrozenRevision, ...]:
    return SnapshotStore(db).list_frozen(required_text(station_id, 'station_id'))


def select_frozen_revision(db: sqlite3.Connection, station_id: str, revision_id: str) -> FrozenRevision:
    return SnapshotStore(db).get(
        required_text(station_id, 'station_id'), required_text(revision_id, 'revision_id')
    )
