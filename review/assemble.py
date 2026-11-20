import sqlite3

from archive.provenance import ParentPieceRef
from archive.publish import PublicationDraft, PublishedReport, publish_report
from exact import RationalInput
from review.admission import admit_pair
from review.overlap import analyze_overlap
from review.request import parse_review_request


def sign(
    db: sqlite3.Connection,
    left_piece: bytes,
    right_piece: bytes,
    threshold: RationalInput,
    lag_min: RationalInput,
    lag_max: RationalInput,
) -> PublishedReport:
    pair = admit_pair(left_piece, right_piece)
    request = parse_review_request(threshold, lag_min, lag_max)
    result = analyze_overlap(pair, request)
    parents = (
        ParentPieceRef(pair.left.station_id, pair.left.revision_id, pair.left.piece_id),
        ParentPieceRef(pair.right.station_id, pair.right.revision_id, pair.right.piece_id),
    )
    draft = PublicationDraft(
        request.threshold, request.lag_min, request.lag_max, result.duration, result.optimal_lags, parents
    )
    return publish_report(db, draft)
