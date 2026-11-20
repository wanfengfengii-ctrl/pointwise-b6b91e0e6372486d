import sqlite3

from archive.provenance import load_parents
from archive.publish import PublishedReport, PublishedStopReport
from archive.receipts import load_success_receipt
from archive.reports import load_report
from archive.stop_reports import load_stop_parents, load_stop_receipt, load_stop_report
from exact import required_text


def read(db: sqlite3.Connection, report_id: str) -> PublishedReport:
    required_text(report_id, 'report_id')
    report = load_report(db, report_id)
    return PublishedReport(report, load_parents(db, report_id), load_success_receipt(db, report_id))


def read_stop(db: sqlite3.Connection, report_id: str) -> dict:
    required_text(report_id, 'report_id')
    report = load_stop_report(db, report_id)
    published = PublishedStopReport(report, load_stop_parents(db, report_id), load_stop_receipt(db, report_id))
    return published.as_dict()
