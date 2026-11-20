import sqlite3
from uuid import uuid4

from exact import RationalInput, rational
from issue.codec import StationPiece, encode_piece
from issue.evidence import freeze_evidence
from issue.exposure import single_station_exposure
from issue.store import IssueReceipt as IssueReceipt
from issue.store import StationPieceStore
from revision.catalog import select_frozen_revision


def issue(db: sqlite3.Connection, station_id: str, revision_id: str, threshold: RationalInput) -> IssueReceipt:
    revision = select_frozen_revision(db, station_id, revision_id)
    level = rational(threshold, 'threshold')
    exposure = single_station_exposure(revision, level)
    evidence = freeze_evidence(revision)
    piece = StationPiece(revision.origin.station_id, revision.revision_id, f'piece-{uuid4().hex}', evidence.to_body())
    receipt = IssueReceipt(
        f'issue-{uuid4().hex}', piece.station_id, piece.revision_id, piece.piece_id,
        level, exposure, encode_piece(piece),
    )
    StationPieceStore(db).save_issue(receipt)
    return receipt
