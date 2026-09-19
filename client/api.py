"""Cliente HTTP — camada de comunicação do cliente PySide6 com o servidor FastAPI."""
from __future__ import annotations

import json
import socket
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


def normalize_server_url(url: str) -> str:
    """Normaliza a URL do servidor digitada pelo usuário.

    - adiciona http:// se o esquema estiver faltando;
    - converte literal IPv6 sem esquema/colchetes (fe80::...%25wlan0) para
      a forma correta http://[...]:porta — evita erro de parse.
    """
    u = (url or "").strip().rstrip("/")
    if not u:
        return "http://127.0.0.1:8000"
    if "[" in u or u.split("/")[0].count(":") > 1:  # já tem colchetes ou é literal v6
        if "://" not in u:
            u = f"http://[{u.lstrip('[').rstrip(']')}]"
        return u
    if "://" not in u:
        u = f"http://{u}"
    return u


def _host_port(url: str) -> tuple[str, str, int]:
    """(esquema, host, porta) de uma URL http — trata IPv6 entre colchetes."""
    rest = url.split("://", 1)[1] if "://" in url else url
    scheme = url.split("://", 1)[0] if "://" in url else "http"
    host_port = rest.split("/", 1)[0]
    if "]" in host_port:  # IPv6 literal [xx]:porta
        host, port_s = host_port[1:].split("]", 1)
        port = int(port_s.lstrip(":") or 80)
    elif ":" in host_port:
        host, port_s = host_port.rsplit(":", 1)
        port = int(port_s or 80)
    else:
        host, port = host_port, 80
    return scheme, host, port


def _same_host(a: str, b: str) -> bool:
    return _host_port(a)[1].lower().rstrip(".") == _host_port(b)[1].lower().rstrip(".")


def _mdns_url(url: str) -> str | None:
    """URL equivalente trocando o host literal por hostname.local (mDNS)."""
    scheme, host, port = _host_port(url)
    if host.lower().endswith(".local"):
        return None
    mdns = f"{socket.gethostname().strip().lower().replace(' ', '-')}.local"
    if not mdns or mdns == host.lower().rstrip("."):
        return None
    return f"{scheme}://{mdns}:{port}"


def _url_variants(url: str) -> list[str]:
    """Variações da mesma URL p/ tentar em sequência (demonstração sem ajustes)."""
    scheme, host, port = _host_port(url)
    variants: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        if u and u not in seen:
            seen.add(u)
            variants.append(u)

    add(url)
    if host.lower() in {"localhost", "127.0.0.1", "::1"}:
        mdns = f"{socket.gethostname().strip().lower().replace(' ', '-')}.local"
        if mdns:
            add(f"{scheme}://{mdns}:{port}")
        add(f"{scheme}://[::1]:{port}")
    elif host.lower().endswith(".local"):
        # o mDNS pode não responder na rede: tenta o IP literal da máquina
        for ip in _local_addresses():
            h = f"[{ip}]" if ":" in ip else ip
            add(f"{scheme}://{h}:{port}")
    else:
        literal = host.lstrip("[").rstrip("]")
        if ":" in literal:  # IPv6 literal (GUA/ULA) — tenta o par mDNS também
            mdns_url = _mdns_url(url)
            if mdns_url:
                add(mdns_url)
    return variants


def _local_addresses() -> list[str]:
    """Endereços IP (v6, depois v4) desta máquina p/ fallback do host .local."""
    out: list[str] = []
    proc = Path("/proc/net/if_inet6")  # Linux: lê direto (evita dependência)
    if proc.exists():
        try:
            for line in proc.read_text().splitlines():
                parts = line.split()
                if len(parts) == 6 and parts[3] != "10":
                    out.append(":".join(parts[0][i:i + 4] for i in range(0, 32, 4)))
        except Exception:
            pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
        for info in infos:
            ip = info[4][0]
            if isinstance(ip, str) and ":" in ip:
                ip = ip.split("%")[0]
            if isinstance(ip, str) and ip not in out:
                out.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # sem pacotes; só descobre a rota
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip not in out:
            out.append(ip)
    except Exception:
        pass
    return out


class AudioApi:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 120.0):
        self.base_url = normalize_server_url(base_url)
        self.timeout = timeout
        self._resolved_url: str | None = None  # endereço que respondeu ao /health

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
        # Fallback automático de endereço: se já descobrimos qual variação da URL
        # responde, usa só ela. Senão, testa as variações (mDNS, ::1, IP literal…)
        # e fixa a primeira que responder — o usuário não precisa descobrir nada.
        if self._resolved_url is not None:
            return httpx.Client(base_url=self._resolved_url, timeout=t)
        for url in _url_variants(self.base_url):
            c = httpx.Client(base_url=url, timeout=t)
            try:
                r = c.get("/health", timeout=httpx.Timeout(12.0, connect=5.0))
                if r.is_success:
                    self._resolved_url = url  # trava no endereço que funciona
                    return c
            except httpx.HTTPError:
                pass
            c.close()
        # Nada respondeu: devolve o cliente original (o erro real aparece na chamada)
        return httpx.Client(base_url=self.base_url, timeout=t)

    def _friendly_error(self, e: Exception, action: str) -> str:
        """Traduz erros de rede para mensagens com dicas acionáveis."""
        if isinstance(e, httpx.ConnectTimeout):
            return (f"{action}: tempo esgotado ao conectar em {self.base_url}.\n"
                    "Possíveis causas:\n"
                    "  • servidor não está rodando (na máquina dele: python -m server)\n"
                    "  • firewall bloqueando a porta 8000 no servidor\n"
                    "  • Wi-Fi com 'ap isolamento de cliente' (máquinas não se enxergam)\n"
                    "  • rede sem mDNS: passe o IPv6 do servidor em --server, ex.:\n"
                    "      python -m client.main --server \"http://[fe80::…%25wlan0]:8000\"")
        if isinstance(e, httpx.ConnectError):
            return (f"{action}: não foi possível conectar ao servidor {self.base_url}.\n"
                    "Verifique se o servidor está rodando e acessível (teste "
                    "http://<nome-do-servidor>.local:8000/health no navegador).\n"
                    f"Detalhe: {e}")
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
