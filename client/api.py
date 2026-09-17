"""Cliente HTTP — camada de comunicação do cliente PySide6 com o servidor FastAPI."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

PROCESSING_LABELS = {
    "none": "Sem processamento",
    "normalize": "Normalização de volume",
    "mono": "Converter para mono",
    "speed": "Alterar velocidade",
    "bitrate": "Reduzir taxa de bits",
    "convert": "Converter formato",
}

AUDIO_FILE_FILTER = (
    "Áudio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma *.opus *.aiff *.aif *.webm);;"
    "Todos os arquivos (*.*)"
)


class ApiError(RuntimeError):
    """Erro de comunicação com o servidor."""


class AudioApi:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------- helpers

    def _client(self) -> httpx.Client:
        # Timeouts granulares: conexão falha rápido (rede/host errado),
        # upload (write) e processamento (read) têm limites próprios.
        t = httpx.Timeout(
            self.timeout,          # default (read)
            connect=10.0,          # servidor inacessível falha em ~10s
            write=self.timeout,    # tempo para ENVIAR o arquivo
            read=self.timeout * 2, # tempo para o servidor PROCESSAR e responder
            pool=10.0,
        )
        return httpx.Client(base_url=self.base_url, timeout=t)

    def _friendly_error(self, e: Exception, action: str) -> str:
        """Traduz erros de rede para mensagens com dicas acionáveis."""
        if isinstance(e, httpx.ConnectTimeout):
            return (f"{action}: tempo esgotado ao conectar em {self.base_url}.\n"
                    "Possíveis causas:\n"
                    "  • servidor não está rodando (uvicorn server.main:app --host 0.0.0.0 --port 8000)\n"
                    "  • IP/porta errados na opção --server\n"
                    "  • firewall bloqueando a porta 8000 no servidor\n"
                    "  • Wi-Fi com 'ap isolamento de cliente' (máquinas não se enxergam)")
        if isinstance(e, httpx.ConnectError):
            return (f"{action}: não foi possível conectar ao servidor {self.base_url}.\n"
                    "Verifique se o servidor está rodando e acessível (teste "
                    f"http://<ip-do-servidor>:8000/health no navegador).\nDetalhe: {e}")
        if isinstance(e, httpx.WriteTimeout):
            return (f"{action}: a conexão caiu durante o envio do arquivo (rede lenta/instável).\n"
                    f"Aumente o timeout:  python -m client.main --timeout 300\nDetalhe: {e}")
        if isinstance(e, httpx.ReadTimeout):
            return (f"{action}: o servidor recebeu o arquivo mas demorou demais para responder.\n"
                    "Áudios longos levam mais tempo para processar — aumente o limite:\n"
                    f"  python -m client.main --timeout 300\nDetalhe: {e}")
        if isinstance(e, httpx.TimeoutException):
            return (f"{action}: tempo esgotado ({self.timeout:g}s). "
                    f"Tente --timeout 300 se o arquivo for grande ou a rede lenta.\nDetalhe: {e}")
        return f"{action}: {e}"

    @staticmethod
    def _raise(resp: httpx.Response, action: str) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ApiError(f"{action}: HTTP {resp.status_code} — {detail}")

    # ---------------------------------------------------------------- API

    def health(self) -> dict:
        try:
            r = self._client().get("/health")
        except httpx.HTTPError as e:
            raise ApiError(self._friendly_error(e, "Servidor inacessível")) from e
        self._raise(r, "health")
        return r.json()

    def list_audios(self) -> list[dict]:
        try:
            r = self._client().get("/api/audios")
        except httpx.HTTPError as e:
            raise ApiError(self._friendly_error(e, "Falha ao listar")) from e
        self._raise(r, "list")
        return r.json()

    def upload(self, path: str | Path, processing_type: str, params: dict | None = None) -> dict:
        """Envia o arquivo com o processamento desejado e devolve o registro criado."""
        p = Path(path)
        data = {
            "processing_type": processing_type,
            "params_json": json.dumps(params or {}),
        }
        mime = {
            ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
            ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac",
            ".opus": "audio/opus", ".aiff": "audio/aiff", ".aif": "audio/aiff",
            ".wma": "audio/x-ms-wma", ".webm": "audio/webm",
        }.get(p.suffix.lower(), "application/octet-stream")

        try:
            with self._client() as c:
                with open(p, "rb") as f:
                    r = c.post(
                        "/api/audios/upload",
                        data=data,
                        files={"file": (p.name, f, mime)},
                    )
        except httpx.HTTPError as e:
            raise ApiError(self._friendly_error(e, "Falha no envio")) from e
        self._raise(r, "upload")
        return r.json()

    def delete(self, audio_id: str) -> dict:
        try:
            r = self._client().delete(f"/api/audios/{audio_id}")
        except httpx.HTTPError as e:
            raise ApiError(self._friendly_error(e, "Falha ao excluir")) from e
        self._raise(r, "delete")
        return r.json()

    # ------------------------------------------------------------- URLs

    def file_url(self, audio_id: str, variant: str = "original") -> str:
        return f"{self.base_url}/api/audios/{audio_id}/file?variant={variant}"

    def waveform_url(self, row: dict) -> str | None:
        rel = row.get("path_original")
        if not rel:
            return None
        import re

        wf = re.sub(r"audio\.[^./\\]+$", "waveform.png", rel.replace("\\", "/"))
        return f"{self.base_url}/media/{wf}"

    def fetch_bytes(self, url: str) -> bytes:
        try:
            r = self._client().get(url)
        except httpx.HTTPError as e:
            raise ApiError(self._friendly_error(e, "Falha ao baixar")) from e
        self._raise(r, "download")
        return r.content
