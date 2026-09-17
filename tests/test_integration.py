"""Teste de integração ponta a ponta (servidor em processo via TestClient).

Cobre o fluxo do trabalho:
  upload → FFmpeg → armazenamento AAAA/MM/DD/<uuid>/ → meta.json → waveform
  → histórico → download → stats → DELETE (trash/) → regras de armazenamento.

Uso:  .venv/bin/python tests/test_integration.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Isola armazenamento e banco em diretórios temporários ANTES de importar o app
_tmp_root = Path(tempfile.mkdtemp(prefix="audiolayers_test_"))
os.environ["STORAGE_DIR"] = str(_tmp_root / "storage")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_root / 'test.db'}"
os.environ["ENV_FILE"] = str(_tmp_root / "nonexistent.env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from server.config import settings  # noqa: E402
from server.main import app  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name))
    print(f"{PASS if cond else FAIL} {name}" + (f"  → {extra}" if extra else ""))


# WAV válido gerado pelo FFmpeg (tom de 2s, estéreo 44.1 kHz) — fica em /tmp
WAV = _tmp_root / "tone.wav"
subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
     "-ac", "2", "-ar", "44100", str(WAV)],
    check=True, capture_output=True,
)

# `with` garante que os eventos de startup (init_db) executem
client_ctx = TestClient(app)
client = client_ctx.__enter__()


def main() -> int:
    print(f"\n=== AudioLayers · integração (storage: {settings.STORAGE_DIR}) ===\n")

    # ---------------------------------------------------------- health
    r = client.get("/health")
    check("GET /health → 200", r.status_code == 200, r.text)

    # ------------------------------------------------- upload normalize
    r = client.post("/api/audios/upload",
                    files={"file": ("tom.wav", open(WAV, "rb"), "audio/wav")},
                    data={"processing_type": "normalize"})
    check("POST upload normalize → 200", r.status_code == 200, r.text[:120])
    a = r.json()
    aid = a.get("id", "")

    # ------------------------------------------------ regras de storage
    rec = Path(settings.STORAGE_DIR) / a["path_original"].split("/audio.wav")[0]
    check("pasta = AAAA/MM/DD/<uuid>", rec.parent.parent.parent.parent == Path(settings.STORAGE_DIR)
          and len(rec.name) == 36, str(rec.relative_to(settings.STORAGE_DIR)))
    check("arquivo original audio.wav", (rec / "audio.wav").exists())
    check("waveform.png gerada", (rec / "waveform.png").exists())
    meta = json.loads((rec / "meta.json").read_text())
    check("meta.json com checksum", len(meta.get("checksum_sha256", "")) == 64)
    check("meta.json com params", "processing_params" in meta)
    check("processado existe (audio_processed.wav)",
          (rec / "audio_processed.wav").exists())

    # --------------------------------------------- processamentos vários
    ok_speed = client.post("/api/audios/upload",
                           files={"file": ("t.wav", open(WAV, "rb"), "audio/wav")},
                           data={"processing_type": "speed", "params_json": '{"rate": 2.0}'}).json()
    ok_bitrate = client.post("/api/audios/upload",
                             files={"file": ("t.wav", open(WAV, "rb"), "audio/wav")},
                             data={"processing_type": "bitrate", "params_json": '{"kbps": 64}'}).json()
    ok_convert = client.post("/api/audios/upload",
                             files={"file": ("t.wav", open(WAV, "rb"), "audio/wav")},
                             data={"processing_type": "convert", "params_json": '{"target_ext": "ogg"}'}).json()
    ok_mono = client.post("/api/audios/upload",
                          files={"file": ("t.wav", open(WAV, "rb"), "audio/wav")},
                          data={"processing_type": "mono"}).json()
    speed_meta = json.loads(((Path(settings.STORAGE_DIR) / ok_speed["path_original"]).parent / "meta.json").read_text())
    proc_dur = (speed_meta.get("processed") or {}).get("duration_sec")
    check("speed 2.0 → duração processada ~metade", proc_dur and 0.8 <= proc_dur <= 1.2,
          f"{proc_dur}s (original {ok_speed['duration_sec']}s)")
    check("bitrate → path_processed .mp3", ok_bitrate["path_processed"] and ok_bitrate["path_processed"].endswith(".mp3"),
          ok_bitrate["path_processed"])
    check("convert → path_processed .ogg", ok_convert["path_processed"] and ok_convert["path_processed"].endswith(".ogg"),
          ok_convert["path_processed"])
    check("mono → channels=1 no processado",
          (Path(settings.STORAGE_DIR) / ok_mono["path_original"]).parent.name and
          json.loads(((Path(settings.STORAGE_DIR) / ok_mono["path_original"]).parent / "meta.json").read_text())
          .get("processed", {}).get("channels") == 1)

    # ------------------------------------------------------- histórico
    r = client.get("/api/audios")
    rows = r.json()
    check("GET /api/audios → 5 registros", r.status_code == 200 and len(rows) == 5, str(len(rows)))

    # ------------------------------------------------------- download
    r = client.get(f"/api/audios/{aid}/file", params={"variant": "original"})
    check("GET file original → 200 wav", r.status_code == 200 and r.content[:4] == b"RIFF")
    r = client.get(f"/api/audios/{aid}/file", params={"variant": "processed"})
    check("GET file processed → 200", r.status_code == 200 and len(r.content) > 1000)

    # ---------------------------------------------------------- meta
    r = client.get(f"/api/audios/{aid}/meta")
    check("GET meta → checksum sha256", r.status_code == 200 and len(r.json().get("checksum_sha256", "")) == 64)

    # ---------------------------------------------------------- stats
    r = client.get("/api/stats")
    s = r.json()
    check("GET stats → 5 áudios", s.get("total_audios") == 5, json.dumps(s)[:120])

    # ---------------------------------------------------------- web
    r = client.get("/web/")
    check("GET /web/ → HTML", r.status_code == 200 and b"AudioLayers" in r.content)
    r = client.get("/")
    check("GET / → redirect /web/", r.status_code in (200, 307))

    # --------------------------------------------------- erros tratados
    r = client.post("/api/audios/upload",
                    files={"file": ("t.txt", b"nao sou audio", "text/plain")},
                    data={"processing_type": "none"})
    check("upload .txt → 400", r.status_code == 400, r.json().get("detail", "")[:60])
    r = client.get("/api/audios/00000000-0000-0000-0000-000000000000")
    check("GET id inexistente → 404", r.status_code == 404)

    # ------------------------------------------------- delete → trash/
    r = client.delete(f"/api/audios/{aid}")
    check("DELETE → ok", r.status_code == 200, r.text)
    trash = Path(settings.STORAGE_DIR) / "trash"
    moved = list(trash.glob("*/audio.wav")) if trash.exists() else []
    check("registro movido p/ trash/", len(moved) == 1, str(moved[0].parent.name) if moved else "")
    r = client.get("/api/audios/trash")
    check("GET /api/audios/trash lista 1", len(r.json()) == 1)
    rows = client.get("/api/audios").json()
    check("histórico agora tem 4", len(rows) == 4)

    # ------------------------------------------------------- validação
    print(f"\n{'='*50}\n{sum(p for p, _ in results)}/{len(results)} testes OK · "
          f"{'TUDO CERTO ✅' if all(p for p, _ in results) else 'FALHAS ❌'}\n")
    return 0 if all(p for p, _ in results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        client_ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(_tmp_root, ignore_errors=True)
    raise SystemExit(code)
