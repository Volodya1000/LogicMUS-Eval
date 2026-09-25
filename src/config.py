from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    eval_model: str = "default-eval"
    target_model: str = "default-target"


settings = Settings(eval_model="default-eval", target_model="default-target")
