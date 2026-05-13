from datetime import datetime, timedelta, timezone

from models import UserScoreState, utcnow
from scoring_engine import (
    BASE_SCORE,
    REWARD_CAP_TOTAL,
    apply_carpool_reward,
    apply_penalty,
    apply_weekly_decay,
    reward_headroom,
)


def test_penalty_floor():
    s = UserScoreState("u1", score=2)
    apply_penalty(s, 10, "x")
    assert s.score == 0


def test_decay_only_to_base():
    s = UserScoreState("u1", score=88)
    r = apply_weekly_decay(s, weeks=10)
    assert r.score_after == BASE_SCORE


def test_decay_no_op_above_base():
    s = UserScoreState("u1", score=110)
    r = apply_weekly_decay(s, weeks=5)
    assert r.delta == 0
    assert s.score == 110


def test_reward_cap_rolling_window():
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    s = UserScoreState("u1", score=BASE_SCORE)
    for i in range(10):
        t = now + timedelta(days=i)
        apply_carpool_reward(s, at=t)
    end = now + timedelta(days=9)
    assert s.rolling_reward_total(28, end) <= REWARD_CAP_TOTAL + 1e-6
    assert s.score <= BASE_SCORE + REWARD_CAP_TOTAL + 1e-6


def test_reward_headroom_respects_window_trim():
    s = UserScoreState("u1")
    old = utcnow() - timedelta(days=29)
    s.reward_grants.append((old, 5.0))
    h = reward_headroom(s, utcnow())
    assert h == REWARD_CAP_TOTAL
