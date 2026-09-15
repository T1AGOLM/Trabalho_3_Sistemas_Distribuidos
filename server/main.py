"""Servidor HTTP (FastAPI) — camada de aplicação do sistema em camadas.

Camadas:
  1. Cliente (PySide6)  ──HTTP──▶  2. Servidor (FastAPI + FFmpeg)  ──▶  3. PostgreSQL
                                        └─▶ arquivos em disco (data/storage/AAAA/MM/DD/<uuid>/)
"""
from __future__ import annotations

import json
import shutil
import uuid as uuid_lib
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import ffmpeg_ops, storage
from .config import settings
from .database import DATABASE_KIND, get_db, init_db
from .models import Audio
from .schemas import AudioOut
from .storage import resolve_rel

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sistema Cliente/Servidor em Camadas — Processamento de Áudio",
    description="Envia, processa (FFmpeg) e armazena áudios com metadados em PostgreSQL.",
    version="1.0.0",
    lifespan=lifespan,
)

# Cliente gráfico roda em outra máquina → libera CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parent / "web"
app.mount("/media", StaticFiles(directory=settings.STORAGE_DIR), name="media")
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/web/")


# --------------------------------------------------------------- API: upload

@app.post("/api/audios/upload", response_model=AudioOut)
async def upload_audio(
    file: UploadFile = File(..., description="Arquivo de áudio"),
    processing_type: str = Form("none"),
    params_json: str = Form("{}"),
    db=Depends(get_db),
):
    """Recebe o áudio, aplica o processamento FFmpeg, salva tudo em disco e registra no banco."""
    params = json.loads(params_json or "{}") if params_json else {}
    ext = Path(file.filename or "audio.mp3").suffix.lower().lstrip(".")
    original_name = Path(file.filename or "audio." + ext).name

    if not ext or f".{ext}" not in storage.AUDIO_EXTS:
        raise HTTPException(400, f"Extensão não suportada: '.{ext}'. "
                                 f"Suportadas: {', '.join(sorted(e.lstrip('.') for e in storage.AUDIO_EXTS))}")
    if processing_type not in {"none", "normalize", "mono", "speed", "bitrate", "convert"}:
        raise HTTPException(400, f"Processamento inválido: {processing_type}")

    tmp = settings.STORAGE_DIR / f"_tmp_{uuid_lib.uuid4().hex}_{Path(original_name).name}"
    size_bytes = 0
    try:
        # 1) recebe o upload em disco (streaming)
        with open(tmp, "wb") as f:
            while chunk := await file.read(1 << 20):
                size_bytes += len(chunk)
                f.write(chunk)
        if size_bytes == 0:
            raise HTTPException(400, "Arquivo vazio.")
        if size_bytes > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Arquivo maior que {settings.MAX_UPLOAD_MB} MB.")

        # 2) metadados do original (ffprobe) — em thread, pois é subprocess
        info = await run_in_threadpool(ffmpeg_ops.probe, tmp)

        # 3) pasta definitiva data/storage/AAAA/MM/DD/<uuid>/
        rec_dir, record_id = storage.make_record_dir(ext)
        final = storage.original_path(rec_dir, ext)
        shutil.move(str(tmp), str(final))

        # 4) processamento FFmpeg
        processed_rel = None
        processed_info: dict = {}
        if processing_type != "none":
            target_ext = ext
            if processing_type == "convert":
                target_ext = str(params.get("target_ext", "ogg")).lower().lstrip(".")
            elif processing_type == "bitrate" and ext in {"wav", "flac", "aiff", "aif"}:
                # redução de bits efetiva: fontes sem perdas viram mp3 na taxa alvo
                target_ext = "mp3"
            p_out = storage.processed_path(rec_dir, target_ext)
            try:
                await run_in_threadpool(ffmpeg_ops.process, final, p_out, processing_type, params)
                processed_info = await run_in_threadpool(ffmpeg_ops.probe, p_out)
                processed_rel = storage.to_relative(p_out)
            except ffmpeg_ops.FFmpegError as e:
                shutil.rmtree(rec_dir, ignore_errors=True)
                raise HTTPException(422, f"Falha no processamento FFmpeg: {e}")

        # 5) waveform.png
        waveform_rel = None
        try:
            wf = rec_dir / "waveform.png"
            await run_in_threadpool(ffmpeg_ops.generate_waveform, final, wf)
            waveform_rel = storage.to_relative(wf)
        except Exception:
            pass  # não bloqueia o upload se o waveform falhar

        # 6) meta.json (checksum, parâmetros, tamanhos)
        meta = {
            "id": str(record_id),
            "original_name": original_name,
            "checksum_sha256": storage.sha256_of(final),
            "processing_type": processing_type,
            "processing_params": {k: v for k, v in params.items()} if processing_type != "none" else {},
            "size_bytes_original": size_bytes,
            "size_bytes_processed": p_out.stat().st_size if processed_rel else None,
            "duration_sec": info.get("duration_sec"),
            "sample_rate": info.get("sample_rate"),
            "channels": info.get("channels"),
            "bitrate": info.get("bitrate"),
            "processed": processed_info or None,
            "waveform": waveform_rel,
        }
        await run_in_threadpool(storage.write_meta, rec_dir, meta)

        # 7) registro no PostgreSQL
        row = Audio(
            id=record_id,
            original_name=original_name,
            original_ext=ext,
            mime_type=storage.guess_mime(f".{ext}"),
            size_bytes=size_bytes,
            duration_sec=info.get("duration_sec"),
            sample_rate=info.get("sample_rate"),
            channels=info.get("channels"),
            bitrate=info.get("bitrate"),
            processing_type=processing_type,
            path_original=storage.to_relative(final),
            path_processed=processed_rel,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return AudioOut.from_row(row)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------ API: GET

@app.get("/api/audios", response_model=list[AudioOut])
def list_audios(db=Depends(get_db)):
    """Histórico de áudios enviados (mais recentes primeiro)."""
    return [AudioOut.from_row(r) for r in db.query(Audio).order_by(Audio.created_at.desc()).all()]


@app.get("/api/audios/trash", response_model=list[str])
def list_trash():
    """Conteúdo atual do diretório trash/ (registrado ANTES de /{audio_id})."""
    trash = settings.STORAGE_DIR / "trash"
    if not trash.exists():
        return []
    return sorted(p.name for p in trash.iterdir() if p.is_dir())


@app.get("/api/audios/{audio_id}", response_model=AudioOut)
def get_audio(audio_id: str, db=Depends(get_db)):
    row = db.get(Audio, _parse_uuid(audio_id))
    if not row:
        raise HTTPException(404, "Áudio não encontrado.")
    return AudioOut.from_row(row)


@app.get("/api/audios/{audio_id}/file")
def get_audio_file(audio_id: str, variant: str = "original", db=Depends(get_db)):
    """Download/stream do áudio (variant=original|processed) — usado pelo cliente."""
    row = db.get(Audio, _parse_uuid(audio_id))
    if not row:
        raise HTTPException(404, "Áudio não encontrado.")
    rel = row.path_processed if variant == "processed" else row.path_original
    if not rel:
        raise HTTPException(404, f"Variante '{variant}' não disponível.")
    path = resolve_rel(rel)
    if not path.exists():
        raise HTTPException(404, "Arquivo ausente no disco.")
    return FileResponse(path, media_type=row.mime_type, filename=path.name)


@app.get("/api/audios/{audio_id}/meta")
def get_meta(audio_id: str, db=Depends(get_db)):
    row = db.get(Audio, _parse_uuid(audio_id))
    if not row or not row.path_original:
        raise HTTPException(404, "Áudio não encontrado.")
    return storage.read_meta(resolve_rel(row.path_original).parent)


@app.get("/api/stats")
def stats(db=Depends(get_db)):
    rows = db.query(Audio).all()
    total_size = sum(r.size_bytes or 0 for r in rows)
    total_duration = sum(r.duration_sec or 0 for r in rows)
    return {
        "total_audios": len(rows),
        "total_size_bytes": total_size,
        "total_duration_sec": round(total_duration, 2),
        "processing_counts": _count_by(rows, "processing_type"),
    }


def _count_by(rows, attr):
    out: dict[str, int] = {}
    for r in rows:
        out[getattr(r, attr)] = out.get(getattr(r, attr), 0) + 1
    return out


# --------------------------------------------------------------- API: DELETE

@app.delete("/api/audios/{audio_id}")
def delete_audio(audio_id: str, db=Depends(get_db)):
    """Move a pasta do registro para trash/ e remove o registro do banco."""
    row = db.get(Audio, _parse_uuid(audio_id))
    if not row:
        raise HTTPException(404, "Áudio não encontrado.")
    rec_dir = resolve_rel(row.path_original).parent if row.path_original else None
    if rec_dir and rec_dir.exists():
        storage.move_to_trash(rec_dir)
    db.delete(row)
    db.commit()
    return {"ok": True, "moved_to_trash": rec_dir.name if rec_dir else None}


# ------------------------------------------------------------------- health

@app.get("/health")
def health():
    return {"status": "ok", "database": DATABASE_KIND}


def _parse_uuid(value: str):
    try:
        return uuid_lib.UUID(value)
    except ValueError:
        raise HTTPException(400, "ID inválido (esperado UUID).")
