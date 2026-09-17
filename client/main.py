"""Ponto de entrada do cliente gráfico (PySide6).

Uso:
    python -m client.main [--server http://IP_DO_SERVIDOR:8000] [--timeout SEGUNDOS]

Exemplos:
    python -m client.main                                  # localhost (servidor na mesma máquina)
    python -m client.main --server http://192.168.0.42:8000   # servidor em outra máquina
    python -m client.main --server http://192.168.0.42:8000 --timeout 300
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
        help="URL do servidor (ex.: http://192.168.0.42:8000). Padrão: http://127.0.0.1:8000",
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
