import pytest
from app import ratelimit
from app.config import settings
from fastapi import HTTPException

from tests.helpers import register


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    ratelimit.reset()
    yield
    ratelimit.reset()


def test_limiter_blocks_after_limit(limits_on):
    for _ in range(3):
        ratelimit.check("k", 3, 60)

    with pytest.raises(HTTPException) as e:
        ratelimit.check("k", 3, 60)

    assert e.value.status_code == 429

    ratelimit.check("other-key", 3, 60)


def test_login_bruteforce_is_throttled(new_client, limits_on):
    register(new_client, "victim")

    ratelimit.reset()
    c = new_client()
    codes = [
        c.post(
            "/api/auth/login",
            json={"email": "victim@t.local", "password": "wrong-pass-1"},
        ).status_code
        for _ in range(12)
    ]

    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
