import json
import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import storage
from app.config import settings
from app.models import Video, VideoStatus

log = logging.getLogger("transcode")
_engine = create_engine(
    settings.database_url.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True
)
SyncSession = sessionmaker(_engine, expire_on_commit=False)

BANDWIDTH = {360: 900_000, 720: 3_000_000}
CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".jpg": "image/jpeg",
}


@dataclass
class TranscodeResult:
    duration_sec: int
    files: list[str]


def _run(cmd):
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True, timeout=3600
    ).stdout


def probe(src):
    data = json.loads(
        _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(src),
            ]
        )
    )

    if not data.get("streams"):
        raise ValueError("no video stream")

    st = data["streams"][0]

    return int(st["width"]), int(st["height"]), float(data["format"]["duration"])


def default_transcoder(src, out):
    sw, sh, duration = probe(src)
    heights = [min(360, sh - sh % 2)] + ([720] if sh >= 720 else [])
    master = ["#EXTM3U", "#EXT-X-VERSION:3"]
    files = []

    for h in heights:
        d = out / f"{h}p"
        d.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                f"scale=-2:{h}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-profile:v",
                "main",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "2",
                "-f",
                "hls",
                "-hls_time",
                "4",
                "-hls_playlist_type",
                "vod",
                "-hls_segment_filename",
                str(d / "seg_%05d.ts"),
                str(d / "index.m3u8"),
            ]
        )

        w = int(round(h * sw / sh / 2)) * 2
        master += [
            f"#EXT-X-STREAM-INF:BANDWIDTH={BANDWIDTH.get(h, 900_000)},RESOLUTION={w}x{h}",
            f"{h}p/index.m3u8",
        ]

        files += [str(p.relative_to(out)) for p in sorted(d.iterdir())]

    (out / "master.m3u8").write_text("\n".join(master) + "\n")

    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{min(1.0, duration / 2):.2f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-2",
            str(out / "thumb.jpg"),
        ]
    )

    return TranscodeResult(int(round(duration)), ["master.m3u8", *files, "thumb.jpg"])


def process_video(
    video_id: str | uuid.UUID, *, transcoder=default_transcoder, session_factory=None
):
    SF = session_factory or SyncSession
    vid = uuid.UUID(str(video_id))

    with SF() as s:
        v = s.get(Video, vid)

        if not v or v.status != VideoStatus.processing:
            return

        source_key = v.source_key

    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            out = Path(tmp) / "out"

            out.mkdir()
            storage.download_file(source_key, src)
            res = transcoder(src, out)

            for rel in res.files:
                if rel == "thumb.jpg":
                    key = f"videos/{vid}/thumb.jpg"
                else:
                    key = f"videos/{vid}/hls/{rel}"

                storage.upload_file(
                    out / rel,
                    key,
                    CONTENT_TYPES.get(Path(rel).suffix, "application/octet-stream"),
                )

        with SF() as s:
            v = s.get(Video, vid)

            if v:
                v.status = VideoStatus.ready
                v.duration_sec = res.duration_sec
                v.error = None
                v.hls_prefix = f"videos/{vid}/hls/"
                v.thumb_key = None

                if "thumb.jpg" in res.files:
                    v.thumb_key = f"videos/{vid}/thumb.jpg"

                s.commit()
    except Exception as e:
        log.exception("transcode failed for %s", vid)

        with SF() as s:
            v = s.get(Video, vid)

            if v:
                v.status = VideoStatus.failed
                v.error = str(e)[:500]

                s.commit()


def cleanup_stale_uploads(max_age_hours=24, session_factory=None):
    SF = session_factory or SyncSession
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    n = 0

    with SF() as s:
        stale = (
            s.execute(
                select(Video).where(
                    Video.status == VideoStatus.uploading, Video.created_at < cutoff
                )
            )
            .scalars()
            .all()
        )

        for v in stale:
            try:
                if v.upload_id:
                    storage.abort_multipart(v.source_key, v.upload_id)

                storage.delete_prefix(f"videos/{v.id}/")
            except Exception:
                log.warning("cleanup: s3 error for %s", v.id)

            s.delete(v)
            n += 1

        s.commit()

    return n
