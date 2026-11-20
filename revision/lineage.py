from dataclasses import dataclass

from exact import required_text


@dataclass(frozen=True)
class RevisionOrigin:
    station_id: str
    recording_id: str
    parent_revision_id: str | None


def initial_origin(station_id: str, recording_id: str) -> RevisionOrigin:
    return RevisionOrigin(
        required_text(station_id, 'station_id'),
        required_text(recording_id, 'recording_id'),
        None,
    )


def child_origin(
    parent: RevisionOrigin, parent_revision_id: str, station_id: str, recording_id: str | None
) -> RevisionOrigin:
    if parent.station_id != station_id:
        raise ValueError('correction station differs from its parent')
    if recording_id is not None and recording_id != parent.recording_id:
        raise ValueError('correction recording differs from its parent')
    return RevisionOrigin(
        station_id, parent.recording_id, required_text(parent_revision_id, 'parent_revision_id')
    )
