"""环境配置：全部经环境变量注入，secrets 不落库、不进 git"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "mysql+pymysql://root:root123@localhost:3306/drone_energy"
    redis_url: str = "redis://localhost:6379/0"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_timeout: float = 30.0

    jwt_secret: str = "change-me-in-prod"
    jwt_expire_minutes: int = 480  # 8 小时：覆盖一次演示会话，避免频繁续签
    cors_origins: list[str] = ["http://localhost:5173"]
    ws_heartbeat_interval: int = 30


settings = Settings()
