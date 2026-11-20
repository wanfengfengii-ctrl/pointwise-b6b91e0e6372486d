import json
from dataclasses import dataclass

from exact import required_text


V1_ENVELOPE_VERSION = 1
V2_ENVELOPE_VERSION = 2
_FIELDS = {'version', 'station_id', 'revision_id', 'piece_id', 'body'}


@dataclass(frozen=True)
class StationPiece:
    station_id: str
    revision_id: str
    piece_id: str
    body: dict


def _validate_piece(piece: StationPiece) -> None:
    required_text(piece.station_id, 'station_id')
    required_text(piece.revision_id, 'revision_id')
    required_text(piece.piece_id, 'piece_id')
    if not isinstance(piece.body, dict):
        raise ValueError('station piece body must be an object')


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate station piece field: {key}')
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f'invalid JSON number: {value}')


def _encode_envelope(piece: StationPiece, version: int) -> bytes:
    _validate_piece(piece)
    return json.dumps({
        'version': version,
        'station_id': piece.station_id,
        'revision_id': piece.revision_id,
        'piece_id': piece.piece_id,
        'body': piece.body,
    }, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def encode_piece(piece: StationPiece) -> bytes:
    return _encode_envelope(piece, V1_ENVELOPE_VERSION)


def encode_stop_piece(piece: StationPiece) -> bytes:
    return _encode_envelope(piece, V2_ENVELOPE_VERSION)


def _decode_envelope(data: bytes, version: int) -> StationPiece:
    if not isinstance(data, bytes):
        raise ValueError('station piece must be UTF-8 JSON bytes')
    try:
        envelope = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid station piece JSON') from error
    if not isinstance(envelope, dict) or envelope.keys() != _FIELDS:
        raise ValueError('incomplete or invalid station piece envelope')
    envelope_version = envelope['version']
    if type(envelope_version) is not int or envelope_version != version:
        raise ValueError('unsupported station piece version')
    piece = StationPiece(envelope['station_id'], envelope['revision_id'], envelope['piece_id'], envelope['body'])
    _validate_piece(piece)
    return piece


def decode_piece(data: bytes) -> StationPiece:
    return _decode_envelope(data, V1_ENVELOPE_VERSION)


def decode_stop_piece(data: bytes) -> StationPiece:
    return _decode_envelope(data, V2_ENVELOPE_VERSION)
