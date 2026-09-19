"""Ponto de entrada do cliente gráfico (PySide6).

Uso:
    python -m client.main [--server http://SERVIDOR:8000] [--timeout SEGUNDOS]

Exemplos (o MESMO comando funciona em qualquer máquina/rede):
    python -m client.main                                              # mesmo PC
    python -m client.main --server "http://nome-do-servidor.local:8000"  # mDNS (recomendado)
    python -m client.main --server "http://[fe80::1a2b:…%25wlan0]:8000"  # IPv6 link-local
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m client.main",
        description="Cliente gráfico do sistema de processamento de áudio.",
    )
    parser.add_argument(
        "--server", metavar="URL", default="http://127.0.0.1:8000",
        help=(
            "URL do servidor — mesma forma em qualquer SO/rede: "
            "http://nome-do-servidor.local:8000 (mDNS, não depende de IP — recomendado), "
            "http://[fe80::…%25iface]:8000 (IPv6 link-local: colchetes + %25), "
            "http://[2001:db8::10]:8000 (IPv6 global) ou http://192.168.0.42:8000. "
            "Padrão: http://127.0.0.1:8000"
        ),
    )
    parser.add_argument(
        "--timeout", type=float, default=120.0, metavar="SEG",
        help="Timeout de rede em segundos para upload/processamento (padrão: 120).",
    )
    args = parser.parse_args()

    # Qt precisa ser importado após resolver os argumentos ( permite ajustar env )
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(args.server, timeout=args.timeout)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
