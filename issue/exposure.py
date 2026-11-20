from fractions import Fraction

from exact import RationalInput, rational
from intake.segments import AffineSegment
from revision.snapshots import FrozenRevision


def _exposed_length(segment: AffineSegment, threshold: Fraction) -> Fraction:
    length = segment.end - segment.start
    colder = min(segment.temperature_start, segment.temperature_end)
    hotter = max(segment.temperature_start, segment.temperature_end)
    if hotter <= threshold:
        return Fraction(0)
    if colder >= threshold:
        return length
    return length * (hotter - threshold) / (hotter - colder)


def single_station_exposure(revision: FrozenRevision, threshold: RationalInput) -> Fraction:
    level = rational(threshold, 'threshold')
    return sum((_exposed_length(segment, level) for segment in revision.segments), Fraction(0))
