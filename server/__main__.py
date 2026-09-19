"""Launcher do servidor com socket **dual-stack** (IPv6 + IPv4 no mesmo socket).

Por que não simplesmente `uvicorn --host ::`? Porque o padrão de IPV6_V6ONLY
varia entre sistemas: no Linux/macOS o socket aceita IPv4-mapped (::ffff:a.b.c.d),
mas **no Windows nasce com V6ONLY=1** e escutaria só IPv6. Este launcher força
`IPV6_V6ONLY = 0` antes do bind — mesmo comportamento em qualquer máquina:

    ✅ IPv6 (global/link-local) e IPv4 são aceitos ao mesmo tempo
    ✅ se a rede não tiver IPv6, a conexão cai no IPv4 sem mudar nada
    ✅ um único comando:  python -m server

Uso:
    python -m server [--port 8000] [--reload] [--log-level info]
"""
from __future__ import annotations

import argparse
import socket

import uvicorn

from .config import settings


def _bind_addr(host: str) -> str:
    """Converte HOST (IPv6, IPv4, wildcard ou hostname) em literal IPv6 para o bind.

    - IPv6 literal → ele mesmo;  IPv4/0.0.0.0/*/vazio → '::' (dual-stack cobre tudo);
    - hostname → resolve p/ IPv6 ('localhost' → '::1'); falha → '::' (wildcard).
    """
    h = (host or "").strip().strip("[]") or "::"
    try:
        socket.inet_pton(socket.AF_INET6, h)
        return h
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET, h)
        return "::"  # IPv4 explícito vira dual-stack wildcard (aceita esse IPv4 e mais)
    except OSError:
        pass
    if h.lower() == "localhost":
        return "::1"
    try:
        infos = socket.getaddrinfo(h, None, socket.AF_INET6, socket.SOCK_STREAM)
        return str(infos[0][4][0]).split("%")[0]
    except socket.gaierror:
        return "::"


def make_dual_stack_socket(host: str, port: int) -> socket.socket:
    """Socket AF_INET6 escutando IPv6 **e** IPv4 (IPV6_V6ONLY=0)."""
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)  # dual-stack
    except OSError:
        pass  # SO sem suporte a dual-stack: fica IPv6 puro
    s.bind((_bind_addr(host), port))
    return s


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m server",
        description="Servidor FastAPI com escuta dual-stack (IPv6 + IPv4).",
    )
    parser.add_argument("--port", type=int, default=settings.PORT,
                        help=f"Porta TCP (padrão: {settings.PORT}).")
    parser.add_argument("--reload", action="store_true", help="Auto-reload (dev).")
    parser.add_argument("--log-level", default="info",
                        help="Log do uvicorn (critical/error/warning/info/debug/trace).")
    args = parser.parse_args()

    config = uvicorn.Config("server.main:app", log_level=args.log_level)
    server = uvicorn.Server(config)

    if args.reload:
        # Com --reload o supervisor recria o processo; deixe o uvicorn fazer o bind.
        print("[servidor] --reload: bind pelo uvicorn (sem dual-stack explícito).")
        server.config.host = _bind_addr(settings.HOST)
        server.config.port = args.port
        server.run()
    else:
        sock = make_dual_stack_socket(settings.HOST, args.port)
        server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
