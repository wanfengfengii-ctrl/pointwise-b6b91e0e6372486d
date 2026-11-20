from dataclasses import dataclass

from issue.codec import StationPiece, decode_piece


@dataclass(frozen=True)
class AdmittedPair:
    left: StationPiece
    right: StationPiece


def admit_pair(left_piece: bytes, right_piece: bytes) -> AdmittedPair:
    left = decode_piece(left_piece)
    right = decode_piece(right_piece)
    if left.station_id == right.station_id:
        raise ValueError('a joint review requires two distinct stations')
    if left.piece_id == right.piece_id:
        raise ValueError('a joint review requires two distinct piece IDs')
    return AdmittedPair(left, right)
