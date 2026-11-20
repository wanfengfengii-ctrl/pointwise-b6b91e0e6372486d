import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from issue.codec import decode_piece


@dataclass(frozen=True)
class IssueReceipt:
    receipt_id: str
    station_id: str
    revision_id: str
    piece_id: str
    threshold: Fraction
    exposure: Fraction
    piece_bytes: bytes


class StationPieceStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS station_issues (
                piece_id TEXT PRIMARY KEY NOT NULL,
                receipt_id TEXT UNIQUE NOT NULL,
                threshold TEXT NOT NULL,
                exposure TEXT NOT NULL,
                piece_bytes BLOB NOT NULL
            )
        ''')

    def save_issue(self, receipt: IssueReceipt) -> None:
        piece = decode_piece(receipt.piece_bytes)
        if (piece.station_id, piece.revision_id, piece.piece_id) != (
            receipt.station_id, receipt.revision_id, receipt.piece_id
        ):
            raise ValueError('issue receipt identity differs from its piece')
        with self.db:
            self.db.execute('''
                INSERT INTO station_issues (piece_id, receipt_id, threshold, exposure, piece_bytes)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                receipt.piece_id, receipt.receipt_id, str(receipt.threshold),
                str(receipt.exposure), receipt.piece_bytes,
            ))

    def load_issue(self, piece_id: str) -> IssueReceipt:
        row = self.db.execute('''
            SELECT receipt_id, threshold, exposure, piece_bytes
            FROM station_issues WHERE piece_id = ?
        ''', (piece_id,)).fetchone()
        if row is None:
            raise KeyError(f'unknown issued piece: {piece_id}')
        receipt_id, threshold, exposure, piece_bytes = row
        piece = decode_piece(piece_bytes)
        return IssueReceipt(
            receipt_id, piece.station_id, piece.revision_id, piece.piece_id,
            Fraction(threshold), Fraction(exposure), piece_bytes,
        )
