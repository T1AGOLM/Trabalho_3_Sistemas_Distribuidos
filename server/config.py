"""Configurações centralizadas do servidor (lida de variáveis de ambiente / .env)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", str(BASE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Banco de dados (PostgreSQL por padrão; SQLite como fallback)
    DATABASE_URL: str = "postgresql+psycopg://audio_user:audio_pass@localhost:5432/audio_db"

    # Servidor — '::' = escuta IPv6 e IPv4 (socket dual-stack criado em __main__.py)
    HOST: str = "::"
    PORT: int = 8000

    # Armazenamento em disco
    STORAGE_DIR: Path = BASE_DIR / "data" / "storage"
    MAX_UPLOAD_MB: int = 100


settings = Settings()
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

TRASH_DIRNAME = "trash"          # data/storage/trash  (arquivos marcados p/ exclusão)
DB_FALLBACK_SQLITE = BASE_DIR / "data" / "audio_fallback.db"
