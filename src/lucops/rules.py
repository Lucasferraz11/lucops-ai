from decimal import Decimal, InvalidOperation


def is_positive_amount(value: str) -> bool:
    """Check whether a value is positive and has up to 2 decimal places."""

    try:
        amount = Decimal(value)
    except InvalidOperation:
        return False

    return (
        amount.is_finite()
        and amount > 0
        and amount.as_tuple().exponent >= -2
    )
