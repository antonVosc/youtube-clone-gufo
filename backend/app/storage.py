import boto3
from botocore.client import Config

from app.config import settings

PAGE_SIZE = 16 * 1024 * 1024


def _client(endpoint):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


_internal = None


def internal():
    global _internal

    _internal = _internal or _client(settings.s3_endpoint)

    return _internal


def start_multipart(key, content_type):
    return internal().create_multipart_upload(
        Bucket=settings.s3_bucket, Key=key, ContentType=content_type
    )["UploadId"]


def to_public(url):
    return url.replace(settings.s3_endpoint, settings.s3_public_endpoint, 1)


def presign_part(key, upload_id, part_number):
    return to_public(
        internal().generate_presigned_url(
            "upload_part",
            ExpiresIn=3600,
            Params={
                "Bucket": settings.s3_bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
        )
    )


def presign_get(key, expires=60):
    return to_public(
        internal().generate_presigned_url(
            "upload_part",
            ExpiresIn=3600,
            Params={"Bucket": settings.s3_bucket, "Key": key},
        )
    )


def upload_file(path, key, content_type):
    internal().upload_file(
        str(path), settings.s3_bucket, key, ExtraArgs={"ContentType": content_type}
    )


def download_file(key, path):
    internal().download_file(settings.s3_bucket, key, str(path))


def ensure_bucket():
    c = internal()

    try:
        c.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        c.create_bucket(Bucket=settings.s3_bucket)


def complete_multipart(key, upload_id, parts):
    internal().complete_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


def abort_multipart(key, upload_id):
    internal().abort_multipart_upload(
        Bucket=settings.s3_bucket, Key=key, UploadId=upload_id
    )


def head_size(key):
    return internal().head_object(Bucket=settings.s3_bucket, Key=key)["ContentLength"]


def read_head(key, n=32):
    r = internal().get_object(
        Bucket=settings.s3_bucket, Key=key, Range=f"bytes=0-{n - 1}"
    )

    return r["Body"].read()


def delete_prefix(prefix):
    c = internal()

    for page in c.get_paginator("list_objects_v2").paginate(
        Bucket=settings.s3_bucket, Prefix=prefix
    ):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]

        if objs:
            c.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objs})
