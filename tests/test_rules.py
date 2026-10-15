import pytest

from lucops.rules import is_positive_amount


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("150.00", True),
        ("0.01", True),
        ("10.5", True),
        ("-20.00", False),
        ("0", False),
        ("abc", False),
        ("NaN", False),
        ("Infinity", False),
        ("10.999", False),
        ("0.001", False),
    ],
)
def test_is_positive_amount(value: str, expected: bool):
    result = is_positive_amount(value)

    assert result == expected
