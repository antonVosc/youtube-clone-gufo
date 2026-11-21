import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

BASE = os.environ.get("BASE_URL", "http://nginx").rstrip("/")


def step(msg):
    print(f"  ✓ {msg}", flush=True)


def check(cond, msg):
    if not cond:
        print(f"  ✗ FAIL: {msg}", flush=True)
        sys.exit(1)

    step(msg)


def main():
    c = httpx.Client(base_url=BASE, timeout=60)
    anon = httpx.Client(base_url=BASE, timeout=60)

    for _ in range(60):
        try:
            if c.get("/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            pass

        time.sleep(2)

    check(c.get("/api/health").status_code == 200, "API отвечает через Nginx")
    check(c.get("/docs").status_code == 200, "Swagger доступен на /docs")

    name = "smoke_" + uuid.uuid4().hex[:8]
    r = c.post(
        "/api/auth/register",
        json={
            "email": f"{name}@smoke.local",
            "username": name,
            "password": "smoke-pass-1",
        },
    )
    check(r.status_code == 201, "регистрация")

    r = c.post(
        "/api/auth/login",
        json={"email": f"{name}@smoke.local", "password": "smoke-pass-1"},
    )
    check(r.status_code == 200, "вход")

    auth = {"Authorization": "Bearer " + r.json()["access_token"]}

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "smoke.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=1280x720:rate=25",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=500",
                "-t",
                "5",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(src),
            ],
            check=True,
        )
        data = src.read_bytes()

    r = c.post(
        "/api/videos",
        headers=auth,
        json={
            "title": "Smoke test video",
            "description": "e2e",
            "filename": "smoke.mp4",
            "content_type": "video/mp4",
            "size_bytes": len(data),
        },
    )

    check(r.status_code == 201, "создана сессия загрузки (presigned multipart)")
    init = r.json()
    parts = []

    for i, url in enumerate(init["part_urls"]):
        chunk = data[i * init["part_size"] : (i + 1) * init["part_size"]]
        pr = httpx.put(BASE + url, content=chunk, timeout=120)
        check(
            pr.status_code == 200 and pr.headers.get("etag"),
            f"часть {i + 1}/{len(init['part_urls'])} загружена в хранилище",
        )
        parts.append({"part_number": i + 1, "etag": pr.headers["etag"]})

    vid = init["video_id"]
    r = c.post(
        f"/api/videos/{vid}/upload/complete", headers=auth, json={"parts": parts}
    )
    check(
        r.status_code == 200 and r.json()["status"] == "processing",
        "загрузка завершена, видео в обработке",
    )
    status = "processing"

    for _ in range(90):
        v = c.get(f"/api/videos/{vid}", headers=auth).json()
        status = v["status"]

        if status in ("ready", "failed"):
            break

        time.sleep(2)

    check(status == "ready", f"воркер транскодировал видео в HLS (status={status})")
    check(v["hls_url"] and v["thumb_url"], "есть hls_url и превью")

    m = c.get(v["hls_url"])
    check(
        m.status_code == 200 and "mpegurl" in m.headers.get("content-type", ""),
        "master.m3u8 отдаётся",
    )

    variants = [ln for ln in m.text.splitlines() if ln.endswith(".m3u8")]
    check(len(variants) == 2, "два качества: 360p и 720p")

    base = v["hls_url"].rsplit("/", 1)[0]
    pl = c.get(f"{base}/{variants[0]}")
    seg = [ln for ln in pl.text.splitlines() if ln.endswith(".ts")][0]
    sr = c.get(f"{base}/{variants[0].rsplit('/', 1)[0]}/{seg}")
    check(sr.status_code == 200 and len(sr.content) > 1000, "HLS-сегмент отдаётся")
    check(c.get(v["thumb_url"]).status_code == 200, "превью отдаётся")
    check(
        c.get(f"/media/{vid}/source").status_code == 404, "оригинал наружу не отдаётся"
    )

    r = c.patch(f"/api/videos/{vid}", headers=auth, json={"visibility": "private"})
    check(r.status_code == 200, "видео сделано приватным")
    check(
        anon.get(f"/api/videos/{vid}").status_code == 404,
        "аноним: метаданные приватного видео недоступны",
    )
    check(
        anon.get(v["hls_url"]).status_code == 403,
        "аноним: сегменты приватного видео недоступны",
    )
    check(c.get(v["hls_url"]).status_code == 200, "владелец: приватное видео играет")
    c.patch(f"/api/videos/{vid}", headers=auth, json={"visibility": "public"})
    check(anon.get(v["hls_url"]).status_code == 200, "после публикации аноним смотрит")

    r = c.put(f"/api/videos/{vid}/like", headers=auth, json={"value": 1})
    check(r.json()["likes"] == 1, "лайк")

    r = c.post(
        f"/api/videos/{vid}/comments", headers=auth, json={"text": "Отличное видео!"}
    )
    check(r.status_code == 201, "комментарий")
    check(
        len(anon.get(f"/api/videos/{vid}/comments").json()) == 1,
        "комментарий виден анониму",
    )

    c.post(f"/api/videos/{vid}/view")
    check(
        anon.get(f"/api/videos/{vid}").json()["views_count"] >= 1, "просмотр засчитан"
    )
    check(vid in [x["id"] for x in anon.get("/api/feed").json()], "видео в ленте")
    check(
        vid in [x["id"] for x in anon.get("/api/search", params={"q": "smoke"}).json()],
        "видео находится поиском",
    )

    c.delete(f"/api/videos/{vid}", headers=auth)

    print("SMOKE OK", flush=True)


if __name__ == "__main__":
    main()
