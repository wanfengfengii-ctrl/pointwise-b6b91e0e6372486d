import sqlite3
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class PublicationReceipt:
    report_id: str
    receipt_id: str


def initialize_receipt_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS publication_receipts (
            report_id TEXT PRIMARY KEY NOT NULL REFERENCES signed_reports(report_id),
            receipt_id TEXT UNIQUE NOT NULL
        )
    ''')


def write_success_receipt(db: sqlite3.Connection, report_id: str) -> PublicationReceipt:
    receipt = PublicationReceipt(report_id, f'signed-{uuid4().hex}')
    db.execute(
        'INSERT INTO publication_receipts (report_id, receipt_id) VALUES (?, ?)',
        (receipt.report_id, receipt.receipt_id),
    )
    return receipt


def load_success_receipt(db: sqlite3.Connection, report_id: str) -> PublicationReceipt:
    row = db.execute('SELECT receipt_id FROM publication_receipts WHERE report_id = ?', (report_id,)).fetchone()
    if row is None:
        raise sqlite3.DatabaseError(f'missing success receipt for report: {report_id}')
    return PublicationReceipt(report_id, row[0])
