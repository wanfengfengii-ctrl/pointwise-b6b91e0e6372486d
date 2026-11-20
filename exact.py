from fractions import Fraction


RationalInput = int | str | Fraction


def rational(value: RationalInput, name: str) -> Fraction:
    if type(value) not in (int, str, Fraction):
        raise ValueError(f'{name} must be an exact rational')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'{name} must be an exact rational') from error


def required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be nonempty text')
    return value
