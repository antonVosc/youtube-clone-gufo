import shutil
import subprocess

import pytest
from app.transcode import default_transcoder, process_video

from tests.helpers import make_video, register

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg is not installed"
)


def _sample(path, size="1280x720", audio=True):
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate=25",
    ]

    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440"]

    cmd += (
        ["-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        + (["-c:a", "aac", "-shortest"] if audio else [])
        + [str(path)]
    )

    subprocess.run(cmd, check=True)


def test_720p_source_gets_two_renditions_and_thumbnail(tmp_path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out"

    out.mkdir()
    _sample(src)
    res = default_transcoder(src, out)
    master = (out / "master.m3u8").read_text()

    assert (
        "360p/index.m3u8" in master
        and "720p/index.m3u8" in master
        and "RESOLUTION=1280x720" in master
    )

    assert (out / "thumb.jpg").stat().st_size > 0 and "thumb.jpg" in res.files
    assert any(f.endswith(".ts") for f in res.files) and res.duration_sec == 3


def test_small_source_without_audio(tmp_path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out"

    out.mkdir()

    _sample(src, size="320x240", audio=False)
    default_transcoder(src, out)
    master = (out / "master.m3u8").read_text()

    assert "720p" not in master and "RESOLUTION=320x240" in master


def test_garbage_input_fails_cleanly(new_client, fake):
    a = register(new_client, "alice")
    vid = make_video(a, fake, ready=False)

    process_video(vid)

    assert a.client.get(f"/api/videos/{vid}", headers=a.h).json()["status"] == "failed"
