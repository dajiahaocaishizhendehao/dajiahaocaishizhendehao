"""应用配置。

所有可变配置通过环境变量注入，代码中不硬编码真实连接串或密钥。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "知识产权管理系统"
    environment: str = "local"
    api_prefix: str = "/api"

    # 允许跨域访问的前端来源；生产环境通过 CORS_ORIGINS 环境变量覆盖为具体域名。
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    database_url: str = "postgresql+psycopg://ipms:ipms@localhost:5432/ipms"

    # 本地文件存储根目录；后续切换对象存储时替换 storage 实现即可。
    storage_root: Path = BASE_DIR / "var" / "storage"

    # 登录会话有效期（分钟）
    session_ttl_minutes: int = 12 * 60

    # 首页“即将到期”默认统计窗口（天）。该值必须随响应一起返回，避免口径不明。
    due_soon_days: int = 30

    # 文件上传限制（字节）
    max_upload_bytes: int = 50 * 1024 * 1024
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
