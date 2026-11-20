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
