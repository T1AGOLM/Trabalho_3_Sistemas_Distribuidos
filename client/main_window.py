"""Janela principal do cliente (PySide6) — camada de apresentação.

Funcionalidades (conforme especificação do trabalho):
  • Seleciona um arquivo de áudio e o processamento desejado
  • Envia o áudio via HTTP para o servidor
  • Reproduz o áudio original e o processado
  • Exibe histórico de arquivos enviados/processados
  • Exibe informações do áudio (duração, formato, tamanho, sample rate…)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QDoubleSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .api import AUDIO_FILE_FILTER, PROCESSING_LABELS, ApiError, AudioApi

ACCENT = "#38bdf8"
ACCENT_2 = "#f472b6"
BG = "#0b0e16"
PANEL = "#111524"
PANEL_2 = "#161b2e"
TXT = "#e7ecf5"
TXT_DIM = "#8b93a7"
OK = "#34d399"
DANGER = "#f87171"

GLOBAL_QSS = f"""
QWidget {{ background: {BG}; color: {TXT}; font-family: 'Segoe UI', 'Ubuntu', sans-serif; }}
QLabel {{ background: transparent; }}
#Header {{
    background: {PANEL}; border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 14px 18px;
}}
#Panel {{
    background: {PANEL}; border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 16px;
}}
#PanelTitle {{
    color: {TXT_DIM}; font-size: 11px; font-weight: 600;
    letter-spacing: 1.5px; text-transform: uppercase; background: transparent;
}}
QPushButton {{
    background: {PANEL_2}; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 10px; padding: 9px 16px; font-size: 13px; color: {TXT};
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:disabled {{ color: {TXT_DIM}; border-color: rgba(255,255,255,0.06); }}
#Primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0ea5e9, stop:1 #6366f1);
    border: none; color: white; font-weight: 600; padding: 11px 18px;
}}
#Primary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #38bdf8, stop:1 #818cf8); }}
#Primary:disabled {{ background: #1e293b; color: {TXT_DIM}; }}
#Danger {{ color: {DANGER}; }}
#Danger:hover {{ border-color: {DANGER}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {PANEL_2}; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 10px; padding: 8px 12px; font-size: 13px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_2}; border: 1px solid rgba(255,255,255,0.12);
    selection-background-color: rgba(56,189,248,0.25);
}}
QTableWidget {{
    background: transparent; border: none; gridline-color: rgba(255,255,255,0.05);
    selection-background-color: rgba(56,189,248,0.18); alternate-background-color: {PANEL_2};
}}
QTableWidget::item {{ padding: 8px; border: none; }}
QHeaderView::section {{
    background: {PANEL_2}; color: {TXT_DIM}; border: none;
    padding: 9px 8px; font-size: 11px; font-weight: 600;
}}
QProgressBar {{
    background: {PANEL_2}; border: none; border-radius: 6px; height: 8px; text-align: center;
}}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2}); border-radius: 6px; }}
QScrollArea {{ border: none; background: transparent; }}
"""


# ─────────────────────────────────────────────────────────────── threads ──

class UploadThread(QThread):
    done = Signal(dict)
    fail = Signal(str)

    def __init__(self, api: AudioApi, file_path: str, processing: str, params: dict, parent=None):
        super().__init__(parent)
        self._api, self._file, self._proc, self._params = api, file_path, processing, params

    def run(self):
        try:
            self.done.emit(self._api.upload(self._file, self._proc, self._params))
        except Exception as e:  # noqa: BLE001
            self.fail.emit(str(e))


class FetchThread(QThread):
    done = Signal(bytes)
    fail = Signal(str)

    def __init__(self, api: AudioApi, url: str, parent=None):
        super().__init__(parent)
        self._api, self._url = api, url

    def run(self):
        try:
            self.done.emit(self._api.fetch_bytes(self._url))
        except Exception as e:  # noqa: BLE001
            self.fail.emit(str(e))


class CallThread(QThread):
    done = Signal(object)
    fail = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # noqa: BLE001
            self.fail.emit(str(e))


# ─────────────────────────────────────────────────────────────── helpers ──

def fmt_size(n) -> str:
    if n is None:
        return "–"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return "–"


def fmt_dur(s) -> str:
    if s is None:
        return "–"
    m, sec = int(s // 60), int(round(s % 60))
    return f"{m}:{sec:02d}"


def fmt_date(iso) -> str:
    if not iso:
        return "–"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(iso)


def _open_with_system_player(path: Path) -> None:
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["start", "", str(path)], shell=True)


# ───────────────────────────────────────────────────────────── main window ──

class MainWindow(QMainWindow):
    def __init__(self, base_url: str):
        super().__init__()
        self.api = AudioApi(base_url)
        self.history: list[dict] = []
        self.selected: dict | None = None
        self._pixmap_original: QPixmap | None = None
        self._tmp_files: list[Path] = []
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)

        self.setWindowTitle("AudioLayers · Cliente")
        self.resize(1120, 720)
        self._build_ui()
        self._check_server()

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # ── Cabeçalho ──
        header = QFrame(objectName="Header")
        hlay = QHBoxLayout(header)
        title_box = QVBoxLayout()
        t1 = QLabel("🎧 AudioLayers — Cliente")
        t1.setStyleSheet("font-size:19px; font-weight:700;")
        self.lbl_server = QLabel("conectando ao servidor…")
        self.lbl_server.setStyleSheet(f"color:{TXT_DIM}; font-size:12px;")
        title_box.addWidget(t1)
        title_box.addWidget(self.lbl_server)
        hlay.addLayout(title_box)
        hlay.addStretch()
        btn_refresh = QPushButton("⟳ Atualizar")
        btn_refresh.clicked.connect(self.refresh_history)
        btn_downloads = QPushButton("📂 Downloads")
        btn_downloads.clicked.connect(self._open_downloads)
        hlay.addWidget(btn_refresh)
        hlay.addWidget(btn_downloads)
        root.addWidget(header)

        # ── Linha principal: esquerda (envio) / direita (detalhes) ──
        cols = QHBoxLayout()
        cols.setSpacing(14)
        root.addLayout(cols, stretch=1)

        # Coluna esquerda
        left = QVBoxLayout()
        left.setSpacing(14)
        cols.addLayout(left, stretch=5)

        left.addWidget(self._build_upload_panel())
        left.addWidget(self._build_history_panel(), stretch=1)

        # Coluna direita
        right = QVBoxLayout()
        right.setSpacing(14)
        cols.addLayout(right, stretch=3)
        right.addWidget(self._build_details_panel(), stretch=1)

    # ------------------------------------------------------- painel envio

    def _build_upload_panel(self) -> QFrame:
        panel = QFrame(objectName="Panel")
        lay = QVBoxLayout(panel)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Enviar áudio", objectName="PanelTitle"))

        row = QHBoxLayout()
        self.edit_file = QLineEdit(placeholderText="Nenhum arquivo selecionado…")
        self.edit_file.setReadOnly(True)
        btn_pick = QPushButton("Procurar…")
        btn_pick.clicked.connect(self._pick_file)
        row.addWidget(self.edit_file, stretch=1)
        row.addWidget(btn_pick)
        lay.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Processamento:"), 0, 0)
        self.combo_proc = QComboBox()
        for key, label in PROCESSING_LABELS.items():
            self.combo_proc.addItem(label, key)
        self.combo_proc.currentIndexChanged.connect(self._update_param_stack)
        grid.addWidget(self.combo_proc, 0, 1)

        # Parâmetros por processamento
        self.stack = QStackedWidget()
        self.stack.setFixedHeight(52)

        page_none = QWidget()
        self.stack.addWidget(page_none)  # idx 0

        # speed → rate
        page_speed = QWidget()
        s = QHBoxLayout(page_speed)
        s.setContentsMargins(0, 0, 0, 0)
        s.addWidget(QLabel("Velocidade (×):"))
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.25, 4.0)
        self.spin_rate.setSingleStep(0.25)
        self.spin_rate.setValue(1.25)
        s.addWidget(self.spin_rate)
        s.addStretch()
        self.stack.addWidget(page_speed)  # idx 1

        # bitrate → kbps
        page_bitrate = QWidget()
        b = QHBoxLayout(page_bitrate)
        b.setContentsMargins(0, 0, 0, 0)
        b.addWidget(QLabel("Taxa de bits (kbps):"))
        self.spin_kbps = QSpinBox()
        self.spin_kbps.setRange(16, 320)
        self.spin_kbps.setValue(96)
        b.addWidget(self.spin_kbps)
        b.addStretch()
        self.stack.addWidget(page_bitrate)  # idx 2

        # convert → formato
        page_convert = QWidget()
        c = QHBoxLayout(page_convert)
        c.setContentsMargins(0, 0, 0, 0)
        c.addWidget(QLabel("Converter para:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["ogg", "mp3", "flac", "wav", "m4a", "opus"])
        c.addWidget(self.combo_format)
        c.addStretch()
        self.stack.addWidget(page_convert)  # idx 3

        grid.addWidget(self.stack, 1, 1)
        lay.addLayout(grid)

        self.btn_send = QPushButton("⬆  Enviar para o servidor", objectName="Primary")
        self.btn_send.clicked.connect(self._send)
        lay.addWidget(self.btn_send)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminada
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        self.lbl_status = QLabel("Pronto.")
        self.lbl_status.setStyleSheet(f"color:{TXT_DIM}; font-size:12px;")
        lay.addWidget(self.lbl_status)
        return panel

    # --------------------------------------------------- painel histórico

    def _build_history_panel(self) -> QFrame:
        panel = QFrame(objectName="Panel")
        lay = QVBoxLayout(panel)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel("Histórico de envios", objectName="PanelTitle"))
        head.addStretch()
        self.edit_search = QLineEdit(placeholderText="🔎 Filtrar por nome…")
        self.edit_search.setMaximumWidth(240)
        self.edit_search.textChanged.connect(self._apply_filter)
        head.addWidget(self.edit_search)
        lay.addLayout(head)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Arquivo", "Processamento", "Duração", "Tamanho", "Enviado em", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.table)
        return panel

    # ---------------------------------------------------- painel detalhes

    def _build_details_panel(self) -> QFrame:
        panel = QFrame(objectName="Panel")
        lay = QVBoxLayout(panel)
        lay.setSpacing(10)

        lay.addWidget(QLabel("Detalhes do áudio", objectName="PanelTitle"))

        self.lbl_name = QLabel("—")
        self.lbl_name.setStyleSheet("font-weight:700; font-size:15px;")
        self.lbl_name.setWordWrap(True)
        lay.addWidget(self.lbl_name)

        form = QFormLayout()
        form.setSpacing(5)
        form.setLabelAlignment(Qt.AlignRight)

        def dim(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color:{TXT_DIM}; font-size:12px;")
            return lbl

        self.detail_labels = {}
        for key, title in [
            ("id", "ID (UUID)"), ("format", "Formato"), ("size", "Tamanho"),
            ("duration", "Duração"), ("sample_rate", "Sample rate"),
            ("channels", "Canais"), ("bitrate", "Bitrate"),
            ("processing", "Processamento"), ("created_at", "Enviado em"),
        ]:
            val = QLabel("—")
            val.setWordWrap(True)
            self.detail_labels[key] = val
            form.addRow(dim(title + ":"), val)
        lay.addLayout(form)

        self.lbl_wave = QLabel("  waveform aparecerá aqui")
        self.lbl_wave.setFixedHeight(90)
        self.lbl_wave.setAlignment(Qt.AlignCenter)
        self.lbl_wave.setStyleSheet(
            f"background:{PANEL_2}; border:1px solid rgba(255,255,255,0.07);"
            f"border-radius:10px; color:{TXT_DIM}; font-size:12px;")
        lay.addWidget(self.lbl_wave)

        btns = QHBoxLayout()
        self.btn_play_orig = QPushButton("▶  Original")
        self.btn_play_orig.clicked.connect(lambda: self._play("original"))
        self.btn_play_proc = QPushButton("▶  Processado")
        self.btn_play_proc.clicked.connect(lambda: self._play("processed"))
        btn_del = QPushButton("🗑 Excluir", objectName="Danger")
        btn_del.clicked.connect(self._delete_selected)
        btns.addWidget(self.btn_play_orig)
        btns.addWidget(self.btn_play_proc)
        btns.addWidget(btn_del)
        lay.addLayout(btns)

        self.lbl_player = QLabel(" ")
        self.lbl_player.setStyleSheet(f"color:{TXT_DIM}; font-size:11px;")
        lay.addWidget(self.lbl_player)
        return panel

    # ------------------------------------------------------------ ações

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar áudio", "", AUDIO_FILE_FILTER)
        if path:
            self.edit_file.setText(path)

    def _update_param_stack(self) -> None:
        key = self.combo_proc.currentData()
        self.stack.setCurrentIndex({"none": 0, "speed": 1, "bitrate": 2, "convert": 3}[key])

    def _current_params(self) -> dict:
        key = self.combo_proc.currentData()
        if key == "speed":
            return {"rate": round(self.spin_rate.value(), 2)}
        if key == "bitrate":
            return {"kbps": self.spin_kbps.value()}
        if key == "convert":
            return {"target_ext": self.combo_format.currentText()}
        return {}

    def _send(self) -> None:
        file_path = self.edit_file.text()
        if not file_path or not Path(file_path).exists():
            QMessageBox.warning(self, "AudioLayers", "Selecione um arquivo de áudio válido.")
            return
        processing = self.combo_proc.currentData()
        params = self._current_params()

        self.btn_send.setEnabled(False)
        self.progress.setVisible(True)
        self.lbl_status.setText("Enviando e processando no servidor…")
        self._upload_thread = UploadThread(self.api, file_path, processing, params)
        self._upload_thread.done.connect(self._on_upload_ok)
        self._upload_thread.fail.connect(self._on_upload_fail)
        self._upload_thread.start()

    def _on_upload_ok(self, row: dict) -> None:
        self.progress.setVisible(False)
        self.btn_send.setEnabled(True)
        name = row.get("original_name", "?")
        self.lbl_status.setText(
            f"✔ '{name}' enviado · processamento: {PROCESSING_LABELS.get(row.get('processing_type'), '—')}")
        self.lbl_status.setStyleSheet(f"color:{OK}; font-size:12px;")
        self.refresh_history()

    def _on_upload_fail(self, err: str) -> None:
        self.progress.setVisible(False)
        self.btn_send.setEnabled(True)
        self.lbl_status.setText("Falha no envio.")
        self.lbl_status.setStyleSheet(f"color:{DANGER}; font-size:12px;")
        QMessageBox.critical(self, "Erro no envio", err)

    def refresh_history(self) -> None:
        self._refresh_thread = CallThread(self.api.list_audios)
        self._refresh_thread.done.connect(self._on_history)
        self._refresh_thread.fail.connect(self._on_history_fail)
        self._refresh_thread.start()

    def _on_history(self, rows: list) -> None:
        self.history = rows
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            item_name = QTableWidgetItem(row.get("original_name", "—"))
            item_name.setData(Qt.UserRole, row)
            values = [
                item_name,
                PROCESSING_LABELS.get(row.get("processing_type"), row.get("processing_type", "—")),
                fmt_dur(row.get("duration_sec")),
                fmt_size(row.get("size_bytes")),
                fmt_date(row.get("created_at")),
                str(row.get("id", ""))[:8],
            ]
            for col, value in enumerate(values):
                if col == 0:
                    continue
                self.table.setItem(i, col, QTableWidgetItem(str(value)))
            self.table.setItem(i, 0, item_name)
        self._apply_filter()
        if not rows:
            self.lbl_status.setText("Histórico vazio — envie seu primeiro áudio.")

    def _on_history_fail(self, err: str) -> None:
        self.lbl_status.setText("Falha ao carregar histórico.")
        self.lbl_status.setStyleSheet(f"color:{DANGER}; font-size:12px;")

    def _apply_filter(self) -> None:
        q = self.edit_search.text().strip().lower()
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            name = item.text().lower() if item else ""
            self.table.setRowHidden(i, bool(q) and q not in name)

    def _on_select(self) -> None:
        sel = self.table.selectedItems()
        if not sel:
            self.selected = None
            return
        row = sel[0].data(Qt.UserRole) or {}
        self.selected = row
        self._fill_details(row)
        self._load_waveform(row)

    def _fill_details(self, row: dict) -> None:
        d = self.detail_labels
        d["id"].setText(str(row.get("id", "—")))
        d["format"].setText(f".{row.get('original_ext', '—')}  ·  {row.get('mime_type', '')}")
        d["size"].setText(fmt_size(row.get("size_bytes")))
        d["duration"].setText(fmt_dur(row.get("duration_sec")))
        d["sample_rate"].setText(
            f"{row.get('sample_rate')} Hz" if row.get("sample_rate") else "—")
        d["channels"].setText(
            f"{row.get('channels')}" + (" (mono)" if row.get("channels") == 1 else " (estéreo)"
                                         if row.get("channels") else ""))
        d["bitrate"].setText(
            f"{row.get('bitrate')} kbps" if row.get("bitrate") else "—")
        d["processing"].setText(
            PROCESSING_LABELS.get(row.get("processing_type"), row.get("processing_type", "—")))
        d["created_at"].setText(fmt_date(row.get("created_at")))
        self.lbl_name.setText(row.get("original_name", "—"))
        self.btn_play_proc.setEnabled(bool(row.get("path_processed")))
        self.btn_play_orig.setEnabled(True)
        self.lbl_player.setText(" ")

    def _load_waveform(self, row: dict) -> None:
        url = self.api.waveform_url(row)
        self._pixmap_original = None
        if not url:
            self.lbl_wave.setText("  waveform indisponível")
            return
        self.lbl_wave.setText("  carregando waveform…")
        self._wave_thread = FetchThread(self.api, url)
        self._wave_thread.done.connect(self._on_waveform)
        self._wave_thread.fail.connect(lambda _e: self.lbl_wave.setText("  waveform indisponível"))
        self._wave_thread.start()

    def _on_waveform(self, data: bytes) -> None:
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.lbl_wave.setText("  waveform indisponível")
            return
        self._pixmap_original = pix
        self._scale_waveform()

    def _scale_waveform(self) -> None:
        if self._pixmap_original:
            self.lbl_wave.setPixmap(
                self._pixmap_original.scaled(
                    self.lbl_wave.width() - 8, self.lbl_wave.height() - 8,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.lbl_wave.setText("")

    def resizeEvent(self, event) -> None:  # redesenha o waveform ao redimensionar
        super().resizeEvent(event)
        self._scale_waveform()

    def _play(self, variant: str) -> None:
        if not self.selected:
            return
        if variant == "processed" and not self.selected.get("path_processed"):
            QMessageBox.information(self, "AudioLayers",
                                    "Este áudio não possui versão processada.")
            return
        url = self.api.file_url(self.selected["id"], variant)
        self._fetch_thread = FetchThread(self.api, url)
        self._fetch_thread.done.connect(lambda data, v=variant: self._play_bytes(data, v))
        self._fetch_thread.fail.connect(self._on_play_fail)
        self._fetch_thread.start()
        self.lbl_player.setText(f"baixando áudio {variant}…")

    def _play_bytes(self, data: bytes, variant: str) -> None:
        # extensão coerente com o arquivo servido (mp3/wav/ogg…)
        row = self.selected or {}
        if variant == "processed":
            ext = Path(row.get("path_processed", "audio_processed.mp3")).suffix or ".mp3"
        else:
            ext = f".{row.get('original_ext', 'mp3')}"
        tmp = Path(tempfile.gettempdir()) / f"audiolayers_{variant}{ext}"
        tmp.write_bytes(data)
        self._tmp_files.append(tmp)
        try:
            self._player.setSource(QUrl.fromLocalFile(str(tmp)))
            self._audio_out.setVolume(0.9)
            self._player.play()
            self.lbl_player.setText(f"▶ reproduzindo {variant}: {row.get('original_name', '')}")
        except Exception:
            _open_with_system_player(tmp)  # fallback: player do sistema
            self.lbl_player.setText(f"▶ reproduzindo com o player do sistema ({variant})")

    def _on_play_fail(self, err: str) -> None:
        self.lbl_player.setText("falha na reprodução")
        QMessageBox.critical(self, "Reprodução", err)

    def _delete_selected(self) -> None:
        if not self.selected:
            return
        row = self.selected
        if QMessageBox.question(
                self, "Excluir áudio",
                f"Mover '{row.get('original_name')}' para trash/ do servidor?") != QMessageBox.Yes:
            return
        try:
            self.api.delete(row["id"])
            self.lbl_status.setText("Áudio movido para trash/ e removido do histórico.")
            self.selected = None
            self._clear_details()
            self.refresh_history()
        except ApiError as e:
            QMessageBox.critical(self, "Erro ao excluir", str(e))

    def _clear_details(self) -> None:
        self.lbl_name.setText("—")
        for lbl in self.detail_labels.values():
            lbl.setText("—")
        self.lbl_wave.setText("  waveform aparecerá aqui")
        self.lbl_wave.setPixmap(QPixmap())
        self.btn_play_orig.setEnabled(False)
        self.btn_play_proc.setEnabled(False)
        self.lbl_player.setText(" ")

    def _open_downloads(self) -> None:
        _open_with_system_player(Path(tempfile.gettempdir()))

    # ----------------------------------------------------------- servidor

    def _check_server(self) -> None:
        self._health_thread = CallThread(self.api.health)
        self._health_thread.done.connect(self._on_health)
        self._health_thread.fail.connect(self._on_health_fail)
        self._health_thread.start()

    def _on_health(self, info: dict) -> None:
        db = info.get("database", "?")
        self.lbl_server.setText(
            f"● conectado — {self.api.base_url}  ·  banco: {db}")
        self.lbl_server.setStyleSheet(f"color:{OK}; font-size:12px;")
        self.btn_play_orig.setEnabled(False)
        self.btn_play_proc.setEnabled(False)
        self.refresh_history()

    def _on_health_fail(self, err: str) -> None:
        self.lbl_server.setText(f"● servidor inacessível em {self.api.base_url}")
        self.lbl_server.setStyleSheet(f"color:{DANGER}; font-size:12px;")
        self.btn_play_orig.setEnabled(False)
        self.btn_play_proc.setEnabled(False)
        self.lbl_status.setText("Sem conexão — verifique se o servidor está em execução.")
        self.lbl_status.setStyleSheet(f"color:{DANGER}; font-size:12px;")
