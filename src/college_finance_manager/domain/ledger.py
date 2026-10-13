from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CashTotals:
    opening_cents: int
    income_cents: int
    expense_cents: int

    @property
    def balance_cents(self) -> int:
        return self.opening_cents + self.income_cents - self.expense_cents

    @property
    def is_negative(self) -> bool:
        return self.balance_cents < 0


def calculate_balance(opening_cents: int, income_cents: int, expense_cents: int) -> int:
    values = (opening_cents, income_cents, expense_cents)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError("余额计算只能使用整数分")
    if income_cents < 0 or expense_cents < 0:
        raise ValueError("收入和支出汇总不能为负数")
    return opening_cents + income_cents - expense_cents
