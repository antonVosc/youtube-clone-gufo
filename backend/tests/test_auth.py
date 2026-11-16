import pytest
from sqlalchemy import text

from tests.helpers import login, register


def test_register_login_me(new_client):
    a = register(new_client, "alice")
    me = a.client.get("/api/auth/me", headers=a.h)

    assert (
        me.status_code == 200
        and me.json()["username"] == "alice"
        and me.json()["role"] == "user"
    )


def test_register_cannot_choose_role(new_client):
    c = new_client()
    r = c.post(
        "/api/auth/register",
        json={
            "email": "x@t.local",
            "username": "xx1",
            "password": "password123",
            "role": "admin",
        },
    )

    assert r.status_code == 201 and r.json()["role"] == "user"


def test_duplicate_email_and_username_case_insensitive(new_client):
    register(new_client, "bob")
    c = new_client()

    assert (
        c.post(
            "/api/auth/register",
            json={
                "email": "bob@t.local",
                "username": "bob2",
                "password": "password123",
            },
        ).status_code
        == 409
    )

    assert (
        c.post(
            "/api/auth/register",
            json={
                "email": "other@t.local",
                "username": "BOB",
                "password": "password123",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "body",
    [
        {"email": "bad", "username": "abc", "password": "password123"},
        {"email": "a@b.cc", "username": "a b", "password": "password123"},
        {"email": "a@b.cc", "username": "abc", "password": "short"},
    ],
)
def test_register_validation(new_client, body):
    assert new_client().post("/api/auth/register", json=body).status_code == 422


def test_wrong_password_and_unknown_user_look_identical(new_client):
    register(new_client, "carol")
    c = new_client()

    r1 = c.post(
        "/api/auth/login", json={"email": "carol@t.local", "password": "nope-nope-1"}
    )
    r2 = c.post(
        "/api/auth/login", json={"email": "ghost@t.local", "password": "nope-nope-1"}
    )

    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()


def test_password_is_hashed_with_argon2(new_client, sync_session):
    register(new_client, "dave")

    with sync_session() as s:
        h = s.execute(
            text("SELECT password_hash FROM users WHERE username='dave'")
        ).scalar_one()

    assert h.startswith("$argon2") and "password123" not in h


def test_protected_endpoints_require_token(new_client):
    c = new_client()

    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/videos", json={}).status_code == 401
    assert (
        c.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code
        == 401
    )


def test_refresh_rotates_and_old_token_is_dead(new_client):
    a = register(new_client, "erin")
    old = [c for c in a.client.cookies.jar if c.name == "refresh_token"][0].value
    r = a.client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]

    replay = new_client()
    replay.cookies.set("refresh_token", old)
    assert replay.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token(new_client):
    a = register(new_client, "frank")
    old = [c for c in a.client.cookies.jar if c.name == "refresh_token"][0].value
    assert a.client.post("/api/auth/logout").status_code == 204

    other = new_client()
    other.cookies.set("refresh_token", old)
    assert other.post("/api/auth/refresh").status_code == 401


def test_deactivated_user_loses_access(new_client, sync_session):
    a = register(new_client, "gina")

    with sync_session() as s:
        s.execute(text("UPDATE users SET is_active=false WHERE username='gina'"))
        s.commit()

    assert a.client.get("/api/auth/me", headers=a.h).status_code == 401
    assert (
        new_client()
        .post(
            "/api/auth/login", json={"email": "gina@t.local", "password": "password123"}
        )
        .status_code
        == 401
    )

    assert login is not None
