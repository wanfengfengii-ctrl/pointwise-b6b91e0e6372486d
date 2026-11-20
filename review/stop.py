from dataclasses import dataclass
from fractions import Fraction

from exact import rational, required_text
from review.request import StopRequest


Interval = tuple[Fraction, Fraction]
AffineRow = tuple[Fraction, Fraction, Fraction, Fraction]
CommandRow = tuple[str, Fraction]


@dataclass(frozen=True)
class StopEvidence:
    batch_id: str
    commands: tuple[CommandRow, ...]
    affine: tuple[AffineRow, ...]


def parse_stop_body(body: object) -> StopEvidence:
    if not isinstance(body, dict) or body.keys() != {'batch_id', 'commands', 'affine'}:
        raise ValueError('invalid stop piece body')
    batch_id = required_text(body['batch_id'], 'batch_id')
    raw_commands = body['commands']
    if not isinstance(raw_commands, list):
        raise ValueError('stop commands must be a list')
    commands = []
    seen = set()
    for row in raw_commands:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError('a stop command row requires a command ID and a time')
        command_id = required_text(row[0], 'command_id')
        if command_id in seen:
            raise ValueError(f'duplicate stop command: {command_id}')
        seen.add(command_id)
        commands.append((command_id, rational(row[1], 'command time')))
    return StopEvidence(batch_id, tuple(commands), _parse_affine(body['affine']))


def _parse_affine(rows: object) -> tuple[AffineRow, ...]:
    if not isinstance(rows, list):
        raise ValueError('invalid affine station evidence')
    affine = []
    previous_end = None
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('an affine evidence row requires four values')
        start, end, slope, intercept = (rational(value, 'affine evidence') for value in row)
        if start >= end or (previous_end is not None and previous_end > start):
            raise ValueError('affine evidence is empty, overlapping, or out of order')
        previous_end = end
        affine.append((start, end, slope, intercept))
    return tuple(affine)


def _window_qualifies(affine: tuple[AffineRow, ...], start: Fraction, end: Fraction, threshold: Fraction) -> bool:
    cursor = start
    for seg_start, seg_end, slope, intercept in affine:
        if seg_end <= cursor:
            continue
        if cursor >= end:
            return True
        if seg_start > cursor:
            return False
        limit = min(seg_end, end)
        if slope * cursor + intercept > threshold or slope * limit + intercept > threshold:
            return False
        cursor = limit
    return cursor >= end


def _eligible_commands(evidence: StopEvidence, request: StopRequest) -> tuple[CommandRow, ...]:
    return tuple(
        (command_id, moment)
        for command_id, moment in evidence.commands
        if _window_qualifies(evidence.affine, moment, moment + request.dwell, request.threshold)
    )


def _max_pairs_at(left_times: list[Fraction], right_times: list[Fraction], lag: Fraction, tolerance: Fraction) -> int:
    adjacency = [
        [index for index, moment in enumerate(right_times) if abs(left - (moment + lag)) <= tolerance]
        for left in left_times
    ]
    match_right = [-1] * len(right_times)

    def augment(left_index: int, seen: list[bool]) -> bool:
        for right_index in adjacency[left_index]:
            if not seen[right_index]:
                seen[right_index] = True
                if match_right[right_index] < 0 or augment(match_right[right_index], seen):
                    match_right[right_index] = left_index
                    return True
        return False

    pairs = 0
    for left_index in range(len(left_times)):
        if augment(left_index, [False] * len(right_times)):
            pairs += 1
    return pairs


def _merge_intervals(intervals: list[Interval]) -> tuple[Interval, ...]:
    merged = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return tuple(merged)


def _optimal_lags(
    left_times: list[Fraction], right_times: list[Fraction], request: StopRequest
) -> tuple[int, tuple[Interval, ...]]:
    window = ((request.lag_min, request.lag_max),)
    if not left_times or not right_times:
        return 0, window
    # An edge between two commands exists exactly on the closed lag interval
    # [left - right - tolerance, left - right + tolerance]. Between consecutive
    # edge endpoints the edge set is constant, and at each endpoint it is a
    # superset of both neighbouring spans, so checking every endpoint plus one
    # interior point per span finds every attainable pair count.
    points = {request.lag_min, request.lag_max}
    for left in left_times:
        for right in right_times:
            for edge in (left - right - request.tolerance, left - right + request.tolerance):
                if request.lag_min < edge < request.lag_max:
                    points.add(edge)
    ordered = sorted(points)
    point_counts = [(point, _max_pairs_at(left_times, right_times, point, request.tolerance)) for point in ordered]
    span_counts = [
        (low, high, _max_pairs_at(left_times, right_times, (low + high) / 2, request.tolerance))
        for low, high in zip(ordered, ordered[1:])
    ]
    best = max([count for _, count in point_counts] + [count for _, _, count in span_counts])
    if best == 0:
        return 0, window
    optimal = [(point, point) for point, count in point_counts if count == best]
    optimal.extend((low, high) for low, high, count in span_counts if count == best)
    return best, _merge_intervals(optimal)


@dataclass(frozen=True)
class StopAnalysis:
    max_pairs: int
    optimal_lags: tuple[Interval, ...]
    eligible_left: tuple[CommandRow, ...]
    eligible_right: tuple[CommandRow, ...]


def analyze_stop(left: StopEvidence, right: StopEvidence, request: StopRequest) -> StopAnalysis:
    eligible_left = _eligible_commands(left, request)
    eligible_right = _eligible_commands(right, request)
    max_pairs, optimal_lags = _optimal_lags(
        [moment for _, moment in eligible_left],
        [moment for _, moment in eligible_right],
        request,
    )
    return StopAnalysis(max_pairs, optimal_lags, eligible_left, eligible_right)
