import time

import pytest

from src.budget import Budget, BudgetExceeded


def test_budget_wall_clock():
    b = Budget(max_wall_s=0.05, max_usd=10, max_iter=100)
    time.sleep(0.08)
    with pytest.raises(BudgetExceeded):
        b.check()


def test_budget_iterations():
    b = Budget(max_wall_s=60, max_usd=10, max_iter=2)
    b.tick_iteration()
    b.tick_iteration()
    with pytest.raises(BudgetExceeded):
        b.tick_iteration()
