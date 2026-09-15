"""Ponto de entrada do cliente gráfico (PySide6).

Uso:
    python -m client.main [--server http://IP_DO_SERVIDOR:8000]
"""
from __future__ import annotations

import sys


def main() -> int:
    base_url = "http://127.0.0.1:8000"
    args = sys.argv[1:]
    if "--server" in args:
        i = args.index("--server")
        if i + 1 < len(args):
            base_url = args[i + 1]

    # Qt precisa ser importado após resolver os argumentos ( permite ajustar env )
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(base_url)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
