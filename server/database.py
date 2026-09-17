"""Camada de acesso ao banco de dados (SQLAlchemy 2.0).

Tenta conectar ao PostgreSQL (DATABASE_URL). Em ambientes onde o PostgreSQL
não está disponível (ex.: correção rápida da atividade), cai automaticamente
para um banco SQLite local para que o sistema continue funcional — o código
das demais camadas não muda.
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_FALLBACK_SQLITE, settings


class Base(DeclarativeBase):
    pass


def _is_sqlite(url: str) -> bool:
    return url.strip().lower().startswith("sqlite")


def _try_connect(url: str, *, timeout_s: float = 4.0) -> bool:
    """Testa rapidamente se o banco responde."""
    try:
        kwargs: dict = {}
        if not _is_sqlite(url):
            kwargs = {"connect_args": {"connect_timeout": int(timeout_s)}}
        engine = create_engine(url, **kwargs)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def _resolve_database_url() -> tuple[str, str]:
    """Retorna (url_em_uso, tipo). Faz fallback p/ SQLite se o PostgreSQL falhar."""
    # URL já é SQLite → conecta sempre; não passa pelo try do PostgreSQL
    if _is_sqlite(settings.DATABASE_URL):
        DB_FALLBACK_SQLITE.parent.mkdir(parents=True, exist_ok=True)
        return settings.DATABASE_URL, "sqlite"
    if _try_connect(settings.DATABASE_URL):
        return settings.DATABASE_URL, "postgresql"
    print(f"[db] PostgreSQL indisponível — usando fallback SQLite em {DB_FALLBACK_SQLITE}")
    DB_FALLBACK_SQLITE.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DB_FALLBACK_SQLITE}", "sqlite"


DATABASE_URL_IN_USE, DATABASE_KIND = _resolve_database_url()

engine_kwargs: dict = {"pool_pre_ping": True}
if _is_sqlite(DATABASE_URL_IN_USE):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL_IN_USE, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Session:  # dependency do FastAPI
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria a tabela `audios` caso não exista (idempotente)."""
    from . import models  # noqa: F401  (importa p/ registrar metadados)

    Base.metadata.create_all(engine)
    print(f"[db] Tabela 'audios' verificada/criada ({DATABASE_KIND}).")
