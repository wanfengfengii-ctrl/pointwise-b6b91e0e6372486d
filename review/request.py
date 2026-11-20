from dataclasses import dataclass
from fractions import Fraction

from exact import RationalInput, rational


@dataclass(frozen=True)
class ReviewRequest:
    threshold: Fraction
    lag_min: Fraction
    lag_max: Fraction


def parse_review_request(threshold: RationalInput, lag_min: RationalInput, lag_max: RationalInput) -> ReviewRequest:
    level = rational(threshold, 'threshold')
    low = rational(lag_min, 'lag_min')
    high = rational(lag_max, 'lag_max')
    if low > high:
        raise ValueError('lag_min must be at most lag_max')
    return ReviewRequest(level, low, high)


@dataclass(frozen=True)
class StopRequest:
    threshold: Fraction
    dwell: Fraction
    tolerance: Fraction
    lag_min: Fraction
    lag_max: Fraction


def parse_stop_request(
    threshold: RationalInput,
    dwell: RationalInput,
    tolerance: RationalInput,
    lag_min: RationalInput,
    lag_max: RationalInput,
) -> StopRequest:
    level = rational(threshold, 'threshold')
    stay = rational(dwell, 'dwell')
    if stay <= 0:
        raise ValueError('dwell must be positive')
    slack = rational(tolerance, 'tolerance')
    if slack < 0:
        raise ValueError('tolerance must be nonnegative')
    low = rational(lag_min, 'lag_min')
    high = rational(lag_max, 'lag_max')
    if low > high:
        raise ValueError('lag_min must be at most lag_max')
    return StopRequest(level, stay, slack, low, high)
