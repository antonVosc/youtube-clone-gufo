from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    s3_endpoint: str
    s3_public_endpoint: str = "/s3"
    s3_bucket: str = "videos"
    minio_root_user: str
    minio_root_password: str
    jwt_secret: str
    access_ttl_min: int = 15
    refresh_ttl_days: int = 14
    media_ttl_min: int = 60
    max_upload_mb: int = 2048
    rate_limit_enabled: bool = True
    cookie_secure: bool = False
    db_null_pool: bool = False


settings = Settings()
