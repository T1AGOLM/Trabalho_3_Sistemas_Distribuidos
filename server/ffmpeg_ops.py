"""Operações de áudio via FFmpeg (ffprobe/ffmpeg).

Processamentos disponíveis (conforme especificação do trabalho):
  normalize  – normalização de volume (EBU R128, loudnorm)
  mono       – conversão para mono
  speed      – alteração da velocidade de reprodução (0.25x–4.0x)
  bitrate    – redução da taxa de bits
  convert    – conversão de formato (mp3/wav/ogg/flac/m4a/opus)
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .storage import guess_mime

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Extensões suportadas como saída de conversão
CONVERTIBLE_EXTS = ["mp3", "wav", "ogg", "flac", "m4a", "opus"]

LOSSY_EXTS = {"mp3", "ogg", "m4a", "opus", "aac", "wma"}


class FFmpegError(RuntimeError):
    """Erro ao executar um comando do FFmpeg."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise FFmpegError(
            f"{' '.join(cmd[:2])} falhou (código {proc.returncode}):\n{proc.stderr[-800:]}"
        )
    return proc


# ---------------------------------------------------------------- ffprobe ---

def probe(path: Path) -> dict:
    """Extrai metadados do arquivo de áudio via ffprobe (JSON)."""
    proc = _run([
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    info = json.loads(proc.stdout or "{}")
    stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "audio"), {}
    )
    fmt = info.get("format", {})

    def _int(value) -> int | None:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    return {
        "duration_sec": float(fmt.get("duration")) if fmt.get("duration") else None,
        "sample_rate": _int(stream.get("sample_rate")),
        "channels": _int(stream.get("channels")),
        "bitrate": _int(fmt.get("bit_rate") or stream.get("bit_rate")),
        "codec": stream.get("codec_name"),
    }


# ----------------------------------------------------------- processamento ---

def normalize(src: Path, dst: Path) -> None:
    """Normalização de volume com loudnorm (EBU R128, duas etapas simplificada)."""
    # libopus (usado em .opus e .webm) só aceita 8/12/16/24/48 kHz — forçar
    # 44100 Hz faz o encoder falhar; os demais formatos ficam em 44100 Hz.
    ar = "48000" if dst.suffix.lower() in {".opus", ".webm"} else "44100"
    _run([
        FFMPEG, "-y", "-i", str(src),
        "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
        "-ar", ar, str(dst),
    ])


def to_mono(src: Path, dst: Path) -> None:
    _run([FFMPEG, "-y", "-i", str(src), "-ac", "1", str(dst)])


def change_speed(src: Path, dst: Path, rate: float = 1.25) -> None:
    """Altera a velocidade mantendo o pitch (atempo encadeado p/ 0.25x–4.0x)."""
    rate = max(0.25, min(4.0, float(rate)))
    # atempo aceita 0.5–2.0 por instância → encadeia filtros p/ cobrir a faixa toda
    tempos: list[float] = []
    r = rate
    while r > 2.0:
        tempos.append(2.0)
        r /= 2.0
    while r < 0.5:
        tempos.append(0.5)
        r /= 0.5
    tempos.append(round(r, 4))
    filt = ",".join(f"atempo={t}" for t in tempos)
    _run([FFMPEG, "-y", "-i", str(src), "-af", filt, str(dst)])


def reduce_bitrate(src: Path, dst: Path, kbps: int = 96) -> None:
    """Reduz a taxa de bits.

    Em fontes sem perdas (wav/flac/…) o destino deve ser .mp3 para a redução
    ser efetiva — o chamador decide a extensão do destino.
    """
    kbps = max(16, min(320, int(kbps)))
    if dst.suffix.lower() == ".mp3":
        _run([FFMPEG, "-y", "-i", str(src), "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(dst)])
    else:
        _run([FFMPEG, "-y", "-i", str(src), "-b:a", f"{kbps}k", str(dst)])


def convert_format(src: Path, dst: Path, target_ext: str = "ogg") -> None:
    """Converte o formato do arquivo (usa -q:a p/ Vorbis e libmp3lame p/ mp3)."""
    target = target_ext.lower().lstrip(".")
    codec_args: list[str] = []
    if target == "mp3":
        codec_args = ["-codec:a", "libmp3lame", "-q:a", "4"]
    elif target == "ogg":
        codec_args = ["-codec:a", "libvorbis", "-q:a", "4"]
    elif target == "opus":
        codec_args = ["-codec:a", "libopus", "-b:a", "96k"]
    elif target == "m4a":
        codec_args = ["-codec:a", "aac", "-b:a", "128k"]
    elif target == "flac":
        codec_args = ["-codec:a", "flac"]
    elif target == "wav":
        codec_args = ["-codec:a", "pcm_s16le"]
    _run([FFMPEG, "-y", "-i", str(src), *codec_args, str(dst)])


def process(src: Path, dst: Path, processing_type: str, params: dict | None = None) -> dict:
    """Aplica o processamento escolhido e devolve os parâmetros efetivos."""
    params = params or {}
    if processing_type == "normalize":
        normalize(src, dst)
        return {"operation": "normalize", "target_loudness_lufs": -16, "true_peak_db": -1.5}
    if processing_type == "mono":
        to_mono(src, dst)
        return {"operation": "mono", "channels": 1}
    if processing_type == "speed":
        rate = float(params.get("rate", 1.25))
        change_speed(src, dst, rate)
        return {"operation": "speed", "rate": rate}
    if processing_type == "bitrate":
        kbps = int(params.get("kbps", 96))
        reduce_bitrate(src, dst, kbps)
        return {"operation": "bitrate", "kbps": kbps}
    if processing_type == "convert":
        target = str(params.get("target_ext", "ogg")).lower().lstrip(".")
        if target not in CONVERTIBLE_EXTS:
            raise FFmpegError(f"Formato de destino não suportado: {target}")
        convert_format(src, dst, target)
        return {"operation": "convert", "target_ext": target}
    raise FFmpegError(f"Processamento desconhecido: {processing_type}")


# -------------------------------------------------------------- waveform ---

def generate_waveform(src: Path, out_png: Path, width: int = 1000, height: int = 160) -> None:
    """Gera waveform.png decodificando o áudio p/ PCM mono e desenhando com Pillow."""
    from PIL import Image, ImageDraw

    # Etapa 1: FFmpeg decodifica para PCM bruto mono 8 kHz s16le (leve e rápido)
    raw = out_png.with_suffix(".raw")
    try:
        _run([
            FFMPEG, "-y", "-i", str(src), "-ac", "1", "-ar", "8000",
            "-f", "s16le", "-acodec", "pcm_s16le", str(raw),
        ])
        data = raw.read_bytes()
    finally:
        if raw.exists():
            raw.unlink()

    n = len(data) // 2
    if n == 0:
        raise FFmpegError("Áudio vazio ou ilegível para gerar waveform.")

    # Etapa 2: agrega amostras em colunas (min/máx por pixel)
    samples = memoryview(data).cast("h")
    cols = width
    per_col = max(1, n // cols)
    peaks: list[tuple[float, float]] = []
    for c in range(cols):
        start = c * per_col
        end = min(n, start + per_col)
        if start >= end:
            peaks.append((0.0, 0.0))
            continue
        chunk = samples[start:end]
        lo = min(chunk) / 32768.0
        hi = max(chunk) / 32768.0
        peaks.append((lo, hi))

    # Etapa 3: desenha (fundo escuro, barras com gradiente âmbar→rosa)
    W, H = width, height
    mid = H // 2
    img = Image.new("RGB", (W, H), (15, 18, 28))
    draw = ImageDraw.Draw(img)

    def lerp(a: float, b: float, t: float) -> tuple:
        return tuple(int(a + (b - a) * t) for a, b in zip(a, b))

    color_a, color_b = (56, 189, 248), (244, 114, 182)  # sky → pink
    for x, (lo, hi) in enumerate(peaks):
        t = x / max(1, W - 1)
        color = lerp(color_a, color_b, t)
        y_top = int(mid - hi * (H / 2 - 6))
        y_bot = int(mid - lo * (H / 2 - 6))
        if y_bot - y_top < 2:
            y_top, y_bot = mid - 1, mid + 1
        draw.rectangle([x, y_top, x, y_bot], fill=color)

    img.save(out_png, "PNG")


def probe_processed_file(dst: Path) -> dict:
    """Metadados do arquivo processado + mime."""
    info = probe(dst)
    info["mime_type"] = guess_mime(dst.suffix)
    return info
