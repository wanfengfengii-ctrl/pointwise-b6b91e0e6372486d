import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ParentPieceRef:
    station_id: str
    revision_id: str
    piece_id: str


def initialize_parent_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS report_parents (
            report_id TEXT NOT NULL REFERENCES signed_reports(report_id),
            position INTEGER NOT NULL CHECK (position IN (0, 1)),
            station_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            piece_id TEXT NOT NULL,
            PRIMARY KEY (report_id, position),
            UNIQUE (report_id, station_id),
            UNIQUE (report_id, piece_id)
        )
    ''')


def store_parents(
    db: sqlite3.Connection, report_id: str, parents: tuple[ParentPieceRef, ParentPieceRef]
) -> None:
    if len(parents) != 2:
        raise ValueError('a signed report requires two parents')
    db.executemany('''
        INSERT INTO report_parents (report_id, position, station_id, revision_id, piece_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        (report_id, position, parent.station_id, parent.revision_id, parent.piece_id)
        for position, parent in enumerate(parents)
    ))


def load_parents(db: sqlite3.Connection, report_id: str) -> tuple[ParentPieceRef, ParentPieceRef]:
    rows = db.execute('''
        SELECT station_id, revision_id, piece_id FROM report_parents
        WHERE report_id = ? ORDER BY position
    ''', (report_id,)).fetchall()
    if len(rows) != 2:
        raise sqlite3.DatabaseError(f'incomplete parents for report: {report_id}')
    return ParentPieceRef(*rows[0]), ParentPieceRef(*rows[1])
