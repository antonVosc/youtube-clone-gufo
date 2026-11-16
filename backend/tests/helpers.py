import re
from dataclasses import dataclass

from app.transcode import SyncSession, process_video
from sqlalchemy import text

from tests.conftest import fake_transcoder

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@dataclass
class Account:
    client: object
    id: str
    username: str
    token: str
    media_token: str

    @property
    def h(self):
        return {"Authorization": f"Bearer {self.token}"}


def register(new_client, username, role=None, password="password123"):
    c = new_client()

    r = c.post(
        "/api/auth/register",
        json={
            "email": f"{username}@t.local",
            "username": username,
            "password": password,
        },
    )

    assert r.status_code == 201, r.text
    uid = r.json()["id"]

    if role:
        with SyncSession() as s:
            s.execute(
                text("UPDATE users SET role=:r WHERE id=:i"), {"r": role, "i": uid}
            )
            s.commit()

    return login(c, username, password, uid)


def login(c, username, password="password123", uid=None):
    r = c.post(
        "/api/auth/login", json={"email": f"{username}@t.local", "password": password}
    )
    assert r.status_code == 200, r.text

    cookies = " ".join(r.headers.get_list("set-cookie"))
    mt = re.search(r"media_token=([^;]+)", cookies).group(1)
    uid = (
        uid
        or c.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        ).json()["id"]
    )

    return Account(c, uid, username, r.json()["access_token"], mt)


def make_video(acc, fake, title="Video", visibility="public", ready=True, content=MP4):
    r = acc.client.post(
        "/api/videos",
        headers=acc.h,
        json={
            "title": title,
            "visibility": visibility,
            "filename": "a.mp4",
            "content_type": "video/mp4",
            "size_bytes": len(content),
        },
    )

    assert r.status_code == 201, r.text

    d = r.json()
    fake.put_part(d["upload_id"], 1, content)

    r = acc.client.post(
        f"/api/videos/{d['video_id']}/upload/complete",
        headers=acc.h,
        json={"parts": [{"part_number": 1, "etag": '"e1"'}]},
    )

    assert r.status_code == 200, r.text

    if ready:
        process_video(d["video_id"], transcoder=fake_transcoder)

    return d["video_id"]


def media_auth(client, uri, token=None):
    headers = {"X-Original-URI": uri}

    if token:
        headers["Cookie"] = f"media_token={token}"

    return client.get("/api/media/auth", headers=headers)


def ids(resp):
    return [v["id"] for v in resp.json()]
