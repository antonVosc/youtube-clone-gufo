from datetime import datetime, timedelta, timezone

from app.transcode import cleanup_stale_uploads, process_video
from sqlalchemy import text

from tests.conftest import fake_transcoder
from tests.helpers import MP4, make_video, register


def _init(acc, size=len(MP4), ctype="video/mp4"):
    return acc.client.post(
        "/api/videos",
        headers=acc.h,
        json={
            "title": "T",
            "filename": "a.mp4",
            "content_type": ctype,
            "size_bytes": size,
        },
    )


def test_pipeline_init_complete_process_ready(new_client, fake):
    a = register(new_client, "alice")
    r = _init(a)
    d = r.json()
    assert (
        r.status_code == 201
        and len(d["part_urls"]) == 1
        and d["part_urls"][0].startswith("/s3/")
    )

    assert (
        a.client.get(f"/api/videos/{d['video_id']}", headers=a.h).json()["status"]
        == "uploading"
    )

    fake.put_part(d["upload_id"], 1, MP4)
    r = a.client.post(
        f"/api/videos/{d['video_id']}/upload/complete",
        headers=a.h,
        json={"parts": [{"part_number": 1, "etag": "e"}]},
    )

    assert r.status_code == 200 and r.json()["status"] == "processing"
    assert fake.enqueued == [d["video_id"]]

    process_video(d["video_id"], transcoder=fake_transcoder)
    v = a.client.get(f"/api/videos/{d['video_id']}", headers=a.h).json()

    assert v["status"] == "ready" and v["duration_sec"] == 5
    assert v["hls_url"] == f"/media/{d['video_id']}/hls/master.m3u8" and v[
        "thumb_url"
    ].endswith("thumb.jpg")
    assert f"videos/{d['video_id']}/hls/master.m3u8" in fake.objects
    assert f"videos/{d['video_id']}/thumb.jpg" in fake.objects


def test_non_video_bytes_rejected_and_removed(new_client, fake):
    a = register(new_client, "alice")
    d = _init(a, size=100).json()
    fake.put_part(d["upload_id"], 1, b"<html>not a video at all</html>" + b"x" * 70)
    r = a.client.post(
        f"/api/videos/{d['video_id']}/upload/complete",
        headers=a.h,
        json={"parts": [{"part_number": 1, "etag": "e"}]},
    )

    assert r.status_code == 422 and not fake.enqueued
    assert not [k for k in fake.objects if d["video_id"] in k]
    assert (
        a.client.get(f"/api/videos/{d['video_id']}", headers=a.h).json()["status"]
        == "failed"
    )


def test_webm_magic_accepted(new_client, fake):
    a = register(new_client, "alice")
    make_video(a, fake, ready=False, content=b"\x1a\x45\xdf\xa3" + b"\x00" * 40)

    assert len(fake.enqueued) == 1


def test_upload_validation(new_client, fake):
    a = register(new_client, "alice")

    assert _init(a, ctype="application/pdf").status_code == 415
    assert _init(a, size=2 * 1024 * 1024).status_code == 413
    assert _init(a, size=0).status_code == 422


def test_only_owner_can_complete_and_only_once(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    d = _init(a).json()

    fake.put_part(d["upload_id"], 1, MP4)
    body = {"parts": [{"part_number": 1, "etag": "e"}]}

    assert (
        b.client.post(
            f"/api/videos/{d['video_id']}/upload/complete", headers=b.h, json=body
        ).status_code
        == 404
    )

    assert (
        a.client.post(
            f"/api/videos/{d['video_id']}/upload/complete",
            headers=a.h,
            json={"parts": [{"part_number": 2, "etag": "e"}]},
        ).status_code
        == 400
    )

    assert (
        a.client.post(
            f"/api/videos/{d['video_id']}/upload/complete", headers=a.h, json=body
        ).status_code
        == 200
    )

    assert (
        a.client.post(
            f"/api/videos/{d['video_id']}/upload/complete", headers=a.h, json=body
        ).status_code
        == 409
    )


def test_incomplete_upload_is_400(new_client, fake):
    a = register(new_client, "alice")
    d = _init(a).json()
    r = a.client.post(
        f"/api/videos/{d['video_id']}/upload/complete",
        headers=a.h,
        json={"parts": [{"part_number": 1, "etag": "e"}]},
    )

    assert r.status_code == 400


def test_transcoder_failure_marks_failed(new_client, fake):
    a = register(new_client, "alice")
    vid = make_video(a, fake, ready=False)

    def boom(src, out):
        raise RuntimeError("ffmpeg exploded")

    process_video(vid, transcoder=boom)
    v = a.client.get(f"/api/videos/{vid}", headers=a.h).json()

    assert v["status"] == "failed" and v["hls_url"] is None


def test_process_is_idempotent_for_ready_video(new_client, fake):
    a = register(new_client, "alice")
    vid = make_video(a, fake)
    calls = []

    process_video(vid, transcoder=lambda s, o: calls.append(1))

    assert calls == []


def test_owner_edits_and_deletes(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    vid = make_video(a, fake, "Old")

    assert (
        b.client.patch(
            f"/api/videos/{vid}", headers=b.h, json={"title": "Hack"}
        ).status_code
        == 404
    )

    r = a.client.patch(
        f"/api/videos/{vid}",
        headers=a.h,
        json={"title": "New", "visibility": "unlisted"},
    )

    assert r.json()["title"] == "New" and r.json()["visibility"] == "unlisted"
    assert b.client.delete(f"/api/videos/{vid}", headers=b.h).status_code == 404
    assert a.client.delete(f"/api/videos/{vid}", headers=a.h).status_code == 204
    assert a.client.get(f"/api/videos/{vid}", headers=a.h).status_code == 404
    assert not [k for k in fake.objects if vid in k]


def test_stale_uploads_are_cleaned(new_client, fake, sync_session):
    a = register(new_client, "alice")
    stale = _init(a).json()["video_id"]
    fresh = _init(a).json()["video_id"]

    with sync_session() as s:
        s.execute(
            text("UPDATE videos SET created_at=:t WHERE id=:i"),
            {"t": datetime.now(timezone.utc) - timedelta(hours=30), "i": stale},
        )

        s.commit()

    assert cleanup_stale_uploads() == 1
    assert a.client.get(f"/api/videos/{stale}", headers=a.h).status_code == 404
    assert a.client.get(f"/api/videos/{fresh}", headers=a.h).status_code == 200
