import pytest

from college_finance_manager.domain.money import InvalidMoney, format_cents, parse_yuan_to_cents


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0.01", 1), ("12", 1200), ("1,234.56".replace(",", ""), 123456)],
)
def test_parse_yuan_to_cents(text, expected):
    assert parse_yuan_to_cents(text) == expected


@pytest.mark.parametrize("text", ["", "0", "-1", "1.001", "NaN", "Infinity", "abc"])
def test_rejects_invalid_business_amount(text):
    with pytest.raises(InvalidMoney):
        parse_yuan_to_cents(text)


def test_opening_balance_may_be_zero_or_negative():
    assert parse_yuan_to_cents("0", allow_zero=True, allow_negative=True) == 0
    assert parse_yuan_to_cents("-10.25", allow_zero=True, allow_negative=True) == -1025


def test_float_is_never_accepted():
    with pytest.raises(InvalidMoney):
        parse_yuan_to_cents(0.1)  # type: ignore[arg-type]


def test_format_cents():
    assert format_cents(-105) == "-1.05"
