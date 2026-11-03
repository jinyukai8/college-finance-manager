from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class InvalidMoney(ValueError):
    """金额不是可接受的精确人民币金额。"""


_CENT = Decimal("0.01")


def parse_yuan_to_cents(value: str, *, allow_zero: bool = False, allow_negative: bool = False) -> int:
    """把界面输入的元转换为整数分，拒绝浮点和超过两位小数。"""
    if not isinstance(value, str):
        raise InvalidMoney("金额必须以文本形式输入")
    text = value.strip()
    if not text:
        raise InvalidMoney("金额不能为空")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise InvalidMoney("金额格式无效") from exc
    if not amount.is_finite():
        raise InvalidMoney("金额必须是有限数值")
    try:
        quantized = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise InvalidMoney("金额超出允许范围") from exc
    if quantized != amount:
        raise InvalidMoney("金额最多保留两位小数")
    if not allow_negative and amount < 0:
        raise InvalidMoney("金额不能为负数")
    if not allow_zero and amount == 0:
        raise InvalidMoney("金额必须大于零")
    cents = int(amount * 100)
    if not -(2**63) <= cents < 2**63:
        raise InvalidMoney("金额超出允许范围")
    return cents


def format_cents(cents: int) -> str:
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TypeError("金额分必须是整数")
    return f"{Decimal(cents) / 100:.2f}"
