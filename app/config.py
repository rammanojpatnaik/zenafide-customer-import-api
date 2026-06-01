from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    jwt_secret_key: str = "change-this-secret-before-deploying"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    seed_demo_users: bool = True
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"
    operator_email: str = "operator@example.com"
    operator_password: str = "operator123"
    log_level: str = "INFO"
    log_file: str | None = None
    upload_dir: str = "./uploads"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    # Storage backend: "local" (default) or "s3"
    storage_backend: str = "local"
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None  # For non-AWS providers (R2, MinIO, etc.)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
