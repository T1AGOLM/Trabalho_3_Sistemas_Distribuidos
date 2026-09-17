"""Camada de armazenamento em disco.

Estrutura exigida pelo trabalho:
    STORAGE_DIR/
      AAAA/MM/DD/<uuid>/audio.{ext}   (original)
                          audio_processed.{ext}
                          meta.json
                          waveform.png
      trash/                          (arquivos marcados para exclusão)
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import TRASH_DIRNAME, settings

AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus", ".aiff", ".aif", ".webm"}
MIME_BY_EXT = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma", ".opus": "audio/opus", ".aiff": "audio/aiff",
    ".aif": "audio/aiff", ".webm": "audio/webm",
}


def guess_mime(ext: str) -> str:
    return MIME_BY_EXT.get(ext.lower(), "application/octet-stream")


def is_audio_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in AUDIO_EXTS


def make_record_dir(ext: str) -> tuple[Path, uuid.UUID]:
    """Cria data/storage/AAAA/MM/DD/<uuid>/ e retorna (diretório, uuid)."""
    ext = ext.lower().lstrip(".")
    record_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    rec_dir = settings.STORAGE_DIR / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}" / str(record_id)
    rec_dir.mkdir(parents=True, exist_ok=True)
    return rec_dir, record_id


def original_path(rec_dir: Path, ext: str) -> Path:
    """Nome do arquivo armazenado é sempre audio.{ext}."""
    return rec_dir / f"audio.{ext.lower().lstrip('.')}"


def processed_path(rec_dir: Path, ext: str) -> Path:
    return rec_dir / f"audio_processed.{ext.lower().lstrip('.')}"


def write_meta(rec_dir: Path, meta: dict) -> None:
    """Metadados complementares ficam em meta.json (checksum, parâmetros, tamanhos)."""
    (rec_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_meta(rec_dir: Path) -> dict:
    try:
        return json.loads((rec_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_relative(path: Path) -> str:
    """Guarda caminhos relativos a STORAGE_DIR no banco (portabilidade)."""
    try:
        return str(path.relative_to(settings.STORAGE_DIR))
    except ValueError:
        return str(path)


def resolve_rel(rel: str) -> Path:
    return (settings.STORAGE_DIR / rel).resolve()


def move_to_trash(rec_dir: Path) -> Path:
    """Move a pasta do registro para trash/ (exclusão temporária)."""
    trash_root = settings.STORAGE_DIR / TRASH_DIRNAME
    trash_root.mkdir(parents=True, exist_ok=True)
    dest = trash_root / rec_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(rec_dir), str(dest))
    return dest
