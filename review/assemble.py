import sqlite3

from archive.provenance import ParentPieceRef
from archive.publish import (
    PublicationDraft,
    PublishedReport,
    StopPublicationDraft,
    publish_report,
    publish_stop_report,
)
from exact import RationalInput
from review.admission import admit_pair, admit_stop_pair
from review.overlap import analyze_overlap
from review.request import parse_review_request, parse_stop_request
from review.stop import analyze_stop, parse_stop_body


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


def sign_stop(
    db: sqlite3.Connection,
    left_piece: bytes,
    right_piece: bytes,
    threshold: RationalInput,
    dwell: RationalInput,
    tolerance: RationalInput,
    lag_min: RationalInput,
    lag_max: RationalInput,
) -> dict:
    pair = admit_stop_pair(left_piece, right_piece)
    request = parse_stop_request(threshold, dwell, tolerance, lag_min, lag_max)
    left = parse_stop_body(pair.left.body)
    right = parse_stop_body(pair.right.body)
    if left.batch_id != right.batch_id:
        raise ValueError('stop pieces name different batches')
    analysis = analyze_stop(left, right, request)
    parents = (
        ParentPieceRef(pair.left.station_id, pair.left.revision_id, pair.left.piece_id),
        ParentPieceRef(pair.right.station_id, pair.right.revision_id, pair.right.piece_id),
    )
    draft = StopPublicationDraft(
        left.batch_id, request.threshold, request.dwell, request.tolerance,
        request.lag_min, request.lag_max, analysis.max_pairs, analysis.optimal_lags,
        (analysis.eligible_left, analysis.eligible_right), parents,
    )
    return publish_stop_report(db, draft).as_dict()
