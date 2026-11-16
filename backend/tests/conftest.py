import os
import re
import uuid

import psycopg2
import pytest
from app import services_queue, storage
from app.db import Base
from app.main import app
from app.transcode import SyncSession, TranscodeResult, _engine
from fastapi.testclient import TestClient

_base = os.environ["DATABASE_URL"]
_test_url = os.environ.get("TEST_DATABASE_URL") or re.sub(
    r"/([^/?]+)$", r"/\1_test", _base
)

os.environ.update(
    {
        "DATABASE_URL": _test_url,
        "DB_NULL_POOL": "1",
        "RATE_LIMIT_ENABLED": "false",
        "MAX_UPLOAD_MB": "1",
    }
)

for k, v in {
    "REDIS_URL": "redis://localhost:6379/0",
    "S3_ENDPOINT": "http://minio:9000",
    "MINIO_ROOT_USER": "x",
    "MINIO_ROOT_PASSWORD": "y",
    "JWT_SECRET": "test-secret-test-secret-test-secret-1",
}.items():
    os.environ.setdefault(k, v)


def _ensure_db():
    m = re.match(r"postgresql\+\w+://([^:]+):([^@]*)@([^:/]+):?(\d+)?/(.+)", _test_url)
    user, pw, host, port, name = m.groups()
    con = psycopg2.connect(
        user=user, password=pw, host=host, port=port or 5432, dbname="postgres"
    )
    con.autocommit = True

    cur = con.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,))

    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{name}"')

    con.close()


_ensure_db()


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.parts = {}
        self.uploads = {}

    def start_multipart(self, key, content_type):
        uid = uuid.uuid4().hex
        self.uploads[uid] = key

        return uid

    def presign_part(self, key, upload_id, n):
        return f"/s3/videos/{key}?partNumber={n}&uploadId={upload_id}"

    def put_part(self, upload_id, n, data):
        self.parts[(upload_id, n)] = data

    def complete_multipart(self, key, upload_id, parts):
        self.objects[key] = b"".join(
            self.parts[(upload_id, p["PartNumber"])] for p in parts
        )

    def abort_multipart(self, key, upload_id):
        self.uploads.pop(upload_id, None)

    def head_size(self, key):
        return len(self.objects[key])

    def read_head(self, key, n=32):
        return self.objects[key][:n]

    def delete_prefix(self, prefix):
        for k in [k for k in self.objects if k.startswith(prefix)]:
            del self.objects[k]

    def presign_get(self, key, expires=60):
        return f"http://minio:9000/videos/{key}?X-Amz-Signature=fake"

    def upload_file(self, path, key, content_type):
        self.objects[key] = open(path, "rb").read()

    def download_file(self, key, path):
        open(path, "wb").write(self.objects[key])


def fake_transcoder(src, out):
    (out / "360p").mkdir()

    (out / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=900000\n360p/index.m3u8\n"
    )
    (out / "360p" / "index.m3u8").write_text("#EXTM3U\n")
    (out / "360p" / "seg_00000.ts").write_bytes(b"ts")
    (out / "thumb.jpg").write_bytes(b"jpg")

    return TranscodeResult(
        5, ["master.m3u8", "360p/index.m3u8", "360p/seg_00000.ts", "thumb.jpg"]
    )


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)

    yield


@pytest.fixture(autouse=True)
def _clean_db():
    with _engine.begin() as c:
        c.exec_driver_sql("TRUNCATE users, videos CASCADE")

    yield


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    f = FakeStorage()

    for name in (
        "start_multipart",
        "presign_part",
        "complete_multipart",
        "abort_multipart",
        "head_size",
        "read_head",
        "delete_prefix",
        "presign_get",
        "upload_file",
        "download_file",
    ):
        monkeypatch.setattr(storage, name, getattr(f, name))

    f.enqueued = []

    monkeypatch.setattr(services_queue, "enqueue_transcode", f.enqueued.append)

    return f


@pytest.fixture
def new_client():
    clients = []

    def make():
        c = TestClient(app)
        clients.append(c)

        return c

    yield make

    for c in clients:
        c.close()


@pytest.fixture
def sync_session():
    return SyncSession
