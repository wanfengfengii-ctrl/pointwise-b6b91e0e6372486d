from dataclasses import dataclass
from fractions import Fraction

from exact import rational
from review.admission import AdmittedPair
from review.request import ReviewRequest


Interval = tuple[Fraction, Fraction]


@dataclass(frozen=True)
class OverlapResult:
    duration: Fraction
    optimal_lags: tuple[Interval, ...]


def _hot_windows(body: dict, threshold: Fraction) -> list[Interval]:
    if body.keys() != {'affine'} or not isinstance(body['affine'], list):
        raise ValueError('invalid affine station evidence')
    intervals = []
    previous_end = None
    for row in body['affine']:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('an affine evidence row requires four values')
        start, end, slope, intercept = (rational(value, 'affine evidence') for value in row)
        if start >= end or (previous_end is not None and previous_end > start):
            raise ValueError('affine evidence is empty, overlapping, or out of order')
        previous_end = end
        left_hot = slope * start + intercept > threshold
        right_hot = slope * end + intercept > threshold
        if left_hot and right_hot:
            intervals.append((start, end))
        elif left_hot != right_hot:
            crossing = (threshold - intercept) / slope
            intervals.append((start, crossing) if left_hot else (crossing, end))
    return intervals


def _overlap_at(left: list[Interval], right: list[Interval], lag: Fraction) -> Fraction:
    left_index = right_index = 0
    total = Fraction(0)
    while left_index < len(left) and right_index < len(right):
        left_start, left_end = left[left_index]
        raw_start, raw_end = right[right_index]
        right_start, right_end = raw_start + lag, raw_end + lag
        start, end = max(left_start, right_start), min(left_end, right_end)
        if start < end:
            total += end - start
        if left_end <= right_end:
            left_index += 1
        if right_end <= left_end:
            right_index += 1
    return total


def _breakpoints(left: list[Interval], right: list[Interval], request: ReviewRequest) -> list[Fraction]:
    points = {request.lag_min, request.lag_max}
    for left_window in left:
        for right_window in right:
            for left_edge in left_window:
                for right_edge in right_window:
                    lag = left_edge - right_edge
                    if request.lag_min < lag < request.lag_max:
                        points.add(lag)
    return sorted(points)


def analyze_overlap(pair: AdmittedPair, request: ReviewRequest) -> OverlapResult:
    left = _hot_windows(pair.left.body, request.threshold)
    right = _hot_windows(pair.right.body, request.threshold)
    # The overlap length is affine between endpoint coincidences. Equality at
    # both ends of a span therefore proves that the entire span is optimal.
    points = _breakpoints(left, right, request)
    durations = [_overlap_at(left, right, point) for point in points]
    best = max(durations)
    optimal = []
    previous_max = False
    for point, duration in zip(points, durations):
        current_max = duration == best
        if current_max:
            if previous_max:
                optimal[-1] = (optimal[-1][0], point)
            else:
                optimal.append((point, point))
        previous_max = current_max
    return OverlapResult(best, tuple(optimal))
