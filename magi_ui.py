"""
MAGI UI — Interface Visual NERV/JARVIS  [v2 — 2026 Design Upgrade]
PySide6 + OpenGL + Threading

Melhorias aplicadas:
  1. MessageBubble com QTextBrowser + renderização Markdown
  2. SkeletonBubble animado (shimmer) no lugar da QProgressBar
  3. AgentActivityWidget separado do EventLog
  4. InputWidget expansível (QTextEdit, Shift+Enter)
  5. GlassPanel com glassmorphism nos painéis laterais
  6. Confidence Indicator nas respostas AI
  7. AnimatedButton com microinterações físicas
"""
import sys, os, math, time, threading, queue, json, re
from pathlib import Path
from datetime import datetime
from collections import deque

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QTextBrowser, QLineEdit, QPushButton, QLabel, QFrame, QSplitter,
    QScrollArea, QGraphicsDropShadowEffect, QSizePolicy, QProgressBar
)
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QObject, QPropertyAnimation,
    QEasingCurve, QRect, QPointF, QSize, QRectF, Property, QAbstractAnimation
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
    QFont, QFontMetrics, QPainterPath, QConicalGradient, QPalette,
    QTextCursor, QTextCharFormat, QPixmap, QIcon, QKeyEvent
)

# ── Paleta NERV ────────────────────────────────────────────────
C_BG          = QColor("#070910")
C_BG2         = QColor("#0a0d14")
C_PANEL       = QColor("#0d1018")
C_BORDER      = QColor("#1a2035")
C_RED         = QColor("#c8001a")
C_RED_DIM     = QColor("#6a0010")
C_ORANGE      = QColor("#e85d04")
C_CYAN        = QColor("#00d4ff")
C_CYAN_DIM    = QColor("#004d5e")
C_WHITE       = QColor("#e8eaf0")
C_GRAY        = QColor("#3a4050")
C_GREEN       = QColor("#00ff88")
C_YELLOW      = QColor("#ffd60a")
C_ONLINE      = QColor("#00ff88")
C_OFFLINE     = QColor("#c8001a")

FONT_MONO   = QFont("Consolas", 10)
FONT_TITLE  = QFont("Consolas", 8)
FONT_SMALL  = QFont("Consolas", 8)

# ── Event Bus ─────────────────────────────────────────────────
class EventBus(QObject):
    on_user_message   = Signal(str)
    on_ai_token       = Signal(str)
    on_ai_response    = Signal(str)
    on_voice_start    = Signal()
    on_voice_end      = Signal()
    on_audio_chunk    = Signal(float)      # amplitude 0..1
    on_emotion        = Signal(str)
    on_status_update  = Signal(dict)
    on_module_update  = Signal(str, bool)  # nome, ativo

bus = EventBus()

# ── Orbe Animado ───────────────────────────────────────────────
class OrbWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(280, 280)
        self.setMaximumSize(320, 320)
        self._amplitude  = 0.0
        self._phase      = 0.0
        self._pulse      = 0.0
        self._speaking   = False
        self._emotion    = "neutro"
        self._particles  = [(i * 37.0, 0.5 + (i % 5) * 0.1, 0.003 + i * 0.0002)
                            for i in range(24)]
        self._rings      = [0.0, 0.33, 0.66]
        self._glow_alpha = 180

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        bus.on_audio_chunk.connect(self._on_audio)
        bus.on_voice_start.connect(lambda: setattr(self, '_speaking', True))
        bus.on_voice_end.connect(lambda: setattr(self, '_speaking', False))
        bus.on_emotion.connect(lambda e: setattr(self, '_emotion', e))

    def _on_audio(self, amp: float):
        self._amplitude = min(1.0, amp)

    def _tick(self):
        self._phase += 0.02
        if self._speaking:
            self._pulse = min(1.0, self._pulse + 0.05)
        else:
            self._amplitude *= 0.92
            self._pulse = max(0.0, self._pulse - 0.03)
        self._rings = [(r + 0.008) % 1.0 for r in self._rings]
        self._particles = [(a + spd * 360, r, spd)
                          for a, r, spd in self._particles]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), C_BG)

        cx = self.width() / 2
        cy = self.height() / 2
        base_r = min(cx, cy) * 0.38

        emotion_colors = {
            "neutro":    C_CYAN,
            "curioso":   QColor("#00aaff"),
            "satisfeito":C_GREEN,
            "frustrado": C_RED,
            "focado":    C_ORANGE,
            "reflexivo": QColor("#aa44ff"),
        }
        cor = emotion_colors.get(self._emotion, C_CYAN)

        glow_r = base_r * (1.6 + self._amplitude * 0.8 + self._pulse * 0.4)
        grd = QRadialGradient(cx, cy, glow_r)
        grd.setColorAt(0.0, QColor(cor.red(), cor.green(), cor.blue(), 60))
        grd.setColorAt(0.5, QColor(cor.red(), cor.green(), cor.blue(), 20))
        grd.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(grd))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        for ring_t in self._rings:
            ring_r = base_r * (1.1 + ring_t * 1.2)
            alpha  = int(120 * (1.0 - ring_t) * (0.4 + self._amplitude * 0.6))
            pen    = QPen(QColor(cor.red(), cor.green(), cor.blue(), alpha), 1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        for angle_deg, orbit_frac, _ in self._particles:
            orbit_r = base_r * (0.9 + orbit_frac * 0.8 + self._amplitude * 0.3)
            rad     = math.radians(angle_deg)
            px      = cx + orbit_r * math.cos(rad)
            py      = cy + orbit_r * math.sin(rad)
            size    = 2.0 + self._amplitude * 3.0
            alpha   = int(180 + self._amplitude * 75)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(cor.red(), cor.green(), cor.blue(), alpha))
            p.drawEllipse(QPointF(px, py), size, size)

        wave_points = 80
        path = QPainterPath()
        for i in range(wave_points + 1):
            angle_rad = (i / wave_points) * 2 * math.pi
            wave_amp  = self._amplitude * 18 * math.sin(angle_rad * 5 + self._phase * 3)
            r         = base_r + wave_amp
            wx        = cx + r * math.cos(angle_rad)
            wy        = cy + r * math.sin(angle_rad)
            if i == 0:
                path.moveTo(wx, wy)
            else:
                path.lineTo(wx, wy)
        path.closeSubpath()
        wave_pen = QPen(QColor(cor.red(), cor.green(), cor.blue(), 160), 1.5)
        p.setPen(wave_pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        core_r = base_r * (0.72 + self._amplitude * 0.12 + self._pulse * 0.08)
        core_grd = QRadialGradient(cx - core_r * 0.2, cy - core_r * 0.2, core_r * 1.2)
        core_grd.setColorAt(0.0, QColor(cor.red(), cor.green(), cor.blue(), 230))
        core_grd.setColorAt(0.4, QColor(cor.red() // 2, cor.green() // 2, cor.blue() // 2, 180))
        core_grd.setColorAt(1.0, QColor(10, 14, 24, 220))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(core_grd))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        border_alpha = int(180 + self._amplitude * 75)
        p.setPen(QPen(QColor(cor.red(), cor.green(), cor.blue(), border_alpha), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        p.setPen(QPen(QColor(255, 255, 255, 200), 1))
        p.setFont(QFont("Consolas", 14, QFont.Bold))
        p.drawText(QRectF(cx - 40, cy - 12, 80, 24), Qt.AlignCenter, "MAGI")
        p.setFont(QFont("Consolas", 7))
        p.setPen(QPen(QColor(cor.red(), cor.green(), cor.blue(), 180), 1))
        p.drawText(QRectF(cx - 40, cy + 10, 80, 14), Qt.AlignCenter, "NYTHERA · SYSTEM")

        p.end()


# ── Equalizador de barras ──────────────────────────────────────
class EqualizerWidget(QWidget):
    def __init__(self, bars=24):
        super().__init__()
        self.setFixedHeight(48)
        self._bars   = bars
        self._heights = [0.05] * bars
        self._targets = [0.05] * bars
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)
        bus.on_audio_chunk.connect(self._on_audio)
        bus.on_voice_end.connect(self._on_silence)

    def _on_audio(self, amp: float):
        import random
        for i in range(self._bars):
            base = amp * (0.5 + 0.5 * math.sin(i * 0.7 + time.time() * 8))
            self._targets[i] = min(1.0, base + random.uniform(0, amp * 0.3))

    def _on_silence(self):
        self._targets = [0.05] * self._bars

    def _tick(self):
        for i in range(self._bars):
            diff = self._targets[i] - self._heights[i]
            self._heights[i] += diff * 0.3
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), C_BG)
        w = self.width()
        h = self.height()
        bar_w = (w - self._bars * 2) / self._bars

        for i, height_frac in enumerate(self._heights):
            bar_h  = max(3, height_frac * (h - 8))
            x      = i * (bar_w + 2) + 1
            y      = h - bar_h - 4
            alpha  = int(120 + height_frac * 135)
            color  = QColor(0, 212, 255, alpha) if height_frac < 0.7 else QColor(200, 0, 26, alpha)
            p.fillRect(int(x), int(y), int(bar_w), int(bar_h), color)
        p.end()


# ── Status dos módulos ─────────────────────────────────────────
class ModuleStatusWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(220)
        self._modules = {
            "CASPER-3":    True,
            "MELCHIOR-1":  True,
            "BALTHASAR-2": True,
            "ADAM-0":      True,
            "SOURCES":     True,
            "MEMORIA":     True,
            "VOZ":         False,
            "TELA":        False,
        }
        layout = QVBoxLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("◈ MÓDULOS ATIVOS")
        title.setFont(QFont("Consolas", 8, QFont.Bold))
        title.setStyleSheet("color: #00d4ff; letter-spacing: 2px;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2035;")
        layout.addWidget(sep)

        self._labels = {}
        MODULE_SUBTITLES = {
            "CASPER-3":    "A MULHER · SÍNTESE",
            "MELCHIOR-1":  "A CIENTISTA · LÓGICA",
            "BALTHASAR-2": "A MÃE · ÉTICA",
            "ADAM-0":      "O CÓDIGO · DEEPSEEK V3",
            "SOURCES":     "WEB · LOCAL · RAG",
            "MEMORIA":     "SEMÂNTICA · FAISS",
            "VOZ":         "EDGE TTS · STT",
            "TELA":        "VISÃO · GEMINI",
        }
        for name, active in self._modules.items():
            row = QHBoxLayout()
            row.setSpacing(6)
            dot = QLabel("●")
            dot.setFont(QFont("Consolas", 10))
            dot.setFixedWidth(16)
            dot.setAlignment(Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(0)
            lbl = QLabel(name)
            lbl.setFont(QFont("Consolas", 9))
            sub = QLabel(MODULE_SUBTITLES.get(name, ""))
            sub.setFont(QFont("Consolas", 7))
            sub.setStyleSheet("color: #2a4060;")
            col.addWidget(lbl)
            col.addWidget(sub)
            self._update_dot(dot, lbl, active)
            row.addWidget(dot)
            row.addLayout(col)
            row.addStretch()
            layout.addLayout(row)
            self._labels[name] = (dot, lbl)

        layout.addStretch()
        bus.on_module_update.connect(self._on_module_update)

    def _update_dot(self, dot, lbl, active):
        if active:
            dot.setStyleSheet("color: #00ff88;")
            lbl.setStyleSheet("color: #a0aab8;")
        else:
            dot.setStyleSheet("color: #3a4050;")
            lbl.setStyleSheet("color: #3a4050;")

    def _on_module_update(self, name: str, active: bool):
        if name in self._labels:
            dot, lbl = self._labels[name]
            self._update_dot(dot, lbl, active)


# ── Painel de memória/status ───────────────────────────────────
class StatusPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("◈ SISTEMA")
        title.setFont(QFont("Consolas", 8, QFont.Bold))
        title.setStyleSheet("color: #00d4ff; letter-spacing: 2px;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2035;")
        layout.addWidget(sep)

        self._fields = {}
        fields = [
            ("ESTADO",    "CURIOSO"),
            ("SESSÃO",    "0 queries"),
            ("MEMÓRIA",   "0 registros"),
            ("MODELO",    "deepseek-chat"),
            ("LATÊNCIA",  "—"),
            ("TOKENS",    "0"),
            ("UPTIME",    "00:00:00"),
        ]
        for key, val in fields:
            row = QHBoxLayout()
            k = QLabel(f"{key}:")
            k.setFont(QFont("Consolas", 8))
            k.setStyleSheet("color: #3a6080;")
            k.setFixedWidth(72)
            v = QLabel(val)
            v.setFont(QFont("Consolas", 8))
            v.setStyleSheet("color: #00d4ff;")
            row.addWidget(k)
            row.addWidget(v)
            row.addStretch()
            layout.addLayout(row)
            self._fields[key] = v

        layout.addStretch()

        self._start = time.time()
        t = QTimer(self)
        t.timeout.connect(self._tick_uptime)
        t.start(1000)

        bus.on_status_update.connect(self._on_status)

    def _tick_uptime(self):
        elapsed = int(time.time() - self._start)
        h, r = divmod(elapsed, 3600)
        m, s = divmod(r, 60)
        self._fields["UPTIME"].setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _on_status(self, data: dict):
        EMOTION_COLORS = {
            "curioso":    "#00aaff",
            "satisfeito": "#00ff88",
            "frustrado":  "#c8001a",
            "focado":     "#e85d04",
            "reflexivo":  "#aa44ff",
            "entediado":  "#ffd60a",
        }
        for key, val in data.items():
            if key in self._fields:
                lbl = self._fields[key]
                lbl.setText(str(val))
                if key == "ESTADO":
                    cor = EMOTION_COLORS.get(str(val).lower(), "#00d4ff")
                    lbl.setStyleSheet(f"color: {cor}; font-weight: bold;")


# ══════════════════════════════════════════════════════════════
# MUDANÇA 2 — SkeletonBubble (substitui QProgressBar)
# ══════════════════════════════════════════════════════════════
class SkeletonBubble(QWidget):
    """Placeholder animado com shimmer enquanto AI está processando."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setStyleSheet("background: #050810; border-left: 2px solid #00d4ff;")
        self._shimmer_pos = 0.0   # 0.0 → 1.0, posição horizontal do brilho

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._shimmer_pos = (self._shimmer_pos + 0.012) % 1.3
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#050810"))

        w = self.width()
        margins = 12
        bar_specs = [
            (margins, 14,  int(w * 0.85 - margins * 2), 10),
            (margins, 32,  int(w * 0.65 - margins * 2), 10),
            (margins, 50,  int(w * 0.45 - margins * 2), 10),
        ]

        base_color   = QColor("#0d1520")
        shimmer_peak = QColor(0, 212, 255, 45)

        for x, y, bw, bh in bar_specs:
            # Base rect
            p.setPen(Qt.NoPen)
            p.setBrush(base_color)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bw, bh), 3, 3)
            p.drawPath(path)

            # Shimmer overlay
            shimmer_x = self._shimmer_pos * (w + 120) - 60
            grd = QLinearGradient(shimmer_x - 60, 0, shimmer_x + 60, 0)
            grd.setColorAt(0.0, QColor(0, 0, 0, 0))
            grd.setColorAt(0.5, shimmer_peak)
            grd.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(grd))
            p.drawPath(path)

        p.end()

    def stop(self):
        self._timer.stop()


# ══════════════════════════════════════════════════════════════
# MUDANÇA 6 — Confidence Indicator
# ══════════════════════════════════════════════════════════════
def _calcular_confianca(texto: str) -> int:
    """Retorna 2-5 blocos de confiança baseado em palavras-chave."""
    t = texto.lower()
    if any(w in t for w in ["certamente", "definitely", "com certeza", "absolutamente", "sem dúvida"]):
        return 5
    if any(w in t for w in ["provavelmente", "likely", "acredito", "é provável", "parece que"]):
        return 4
    if any(w in t for w in ["possivelmente", "talvez", "maybe", "pode ser", "é possível"]):
        return 3
    if any(w in t for w in ["incerto", "uncertain", "não sei", "não tenho certeza", "difícil dizer"]):
        return 2
    return 4  # default


# ══════════════════════════════════════════════════════════════
# MUDANÇA 1 — MessageBubble com QTextBrowser + Markdown
# ══════════════════════════════════════════════════════════════
class MessageBubble(QWidget):
    def __init__(self, role: str, text: str = "", ts: str = ""):
        super().__init__()
        self._role = role
        self._token_count = 0
        self._accumulated  = text
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        # Timestamp
        ts_lbl = QLabel(ts or datetime.now().strftime("%H:%M:%S"))
        ts_lbl.setFont(QFont("Consolas", 7))
        ts_lbl.setStyleSheet("color: #2a4060;")
        if role == "user":
            ts_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(ts_lbl)

        # Linha prefixo + conteúdo
        row = QHBoxLayout()
        row.setSpacing(8)

        prefix = QLabel("NERV >>" if role == "user" else "NYTHERA <<")
        prefix.setFont(QFont("Consolas", 9, QFont.Bold))
        prefix.setStyleSheet(
            "color: #c8001a;" if role == "user" else "color: #005580;"
        )
        prefix.setFixedWidth(90)
        prefix.setAlignment(Qt.AlignTop)
        row.addWidget(prefix)

        # ── QTextBrowser para markdown (role ai) ou QLabel (user) ──
        if role == "ai":
            self._browser = QTextBrowser()
            self._browser.setOpenExternalLinks(True)
            self._browser.setReadOnly(True)
            self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._browser.setFrameShape(QFrame.NoFrame)
            self._browser.setStyleSheet("""
                QTextBrowser {
                    background: transparent;
                    color: #c8d0e0;
                    border: none;
                    padding: 0px;
                    font-family: Consolas;
                    font-size: 10pt;
                }
                QScrollBar { width: 0px; height: 0px; }
            """)
            self._browser.document().setDefaultStyleSheet("""
                code {
                    background-color: #0d1520;
                    color: #00d4ff;
                    font-family: Consolas, monospace;
                    font-size: 9pt;
                    padding: 1px 4px;
                    border-radius: 2px;
                }
                pre {
                    background-color: #050810;
                    border-left: 2px solid #c8001a;
                    padding: 8px 12px;
                    margin: 4px 0;
                    font-family: Consolas, monospace;
                    font-size: 9pt;
                    color: #a0b8c8;
                }
                h1, h2, h3 {
                    color: #00d4ff;
                    font-weight: normal;
                    font-family: Consolas;
                    margin: 4px 0 2px 0;
                }
                blockquote {
                    border-left: 2px solid #3a4050;
                    padding-left: 8px;
                    color: #6a7a90;
                    margin: 4px 0;
                }
                a { color: #00d4ff; }
                p { margin: 2px 0; }
            """)
            if text:
                self._browser.setMarkdown(text)
            self._adjust_browser_height()
            row.addWidget(self._browser, stretch=1)
            self._text_lbl = None
        else:
            self._browser = None
            self._text_lbl = QLabel(text)
            self._text_lbl.setFont(QFont("Consolas", 10))
            self._text_lbl.setWordWrap(True)
            self._text_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._text_lbl.setStyleSheet("color: #ffffff;")
            row.addWidget(self._text_lbl, stretch=1)

        layout.addLayout(row)

        # ── MUDANÇA 6: Confidence indicator (oculto até done) ──
        if role == "ai":
            self._conf_row = QHBoxLayout()
            self._conf_row.setContentsMargins(0, 2, 0, 0)
            self._conf_lbl = QLabel()
            self._conf_lbl.setFont(QFont("Consolas", 7))
            self._conf_lbl.setAlignment(Qt.AlignRight)
            self._conf_lbl.setStyleSheet("color: #1a2035;")
            self._conf_lbl.hide()
            self._conf_row.addStretch()
            self._conf_row.addWidget(self._conf_lbl)
            layout.addLayout(self._conf_row)

        # Borda esquerda
        border_color = "#c8001a" if role == "user" else "#00d4ff"
        self.setStyleSheet(f"""
            MessageBubble {{
                background: {"#0d1520" if role == "user" else "#050810"};
                border-left: 2px solid {border_color};
            }}
        """)

    def _adjust_browser_height(self):
        """Redimensiona o QTextBrowser para evitar scroll interno."""
        if self._browser is None:
            return
        doc_size = self._browser.document().size()
        h = int(doc_size.height()) + 8
        self._browser.setMinimumHeight(max(20, h))
        self._browser.setMaximumHeight(max(20, h))

    def append_text(self, token: str):
        self._accumulated += token
        self._token_count += 1
        if self._browser is not None:
            # Renderiza a cada 5 tokens para não quebrar markdown parcial
            if self._token_count % 5 == 0:
                self._browser.setMarkdown(self._accumulated)
                self._adjust_browser_height()
        elif self._text_lbl is not None:
            self._text_lbl.setText(self._accumulated)

    def set_text(self, txt: str):
        self._accumulated = txt
        if self._browser is not None:
            self._browser.setMarkdown(txt)
            self._adjust_browser_height()
        elif self._text_lbl is not None:
            self._text_lbl.setText(txt)

    def show_confidence(self, full_text: str):
        """Mostra o indicador de confiança após a resposta completa."""
        if not hasattr(self, '_conf_lbl'):
            return
        level = _calcular_confianca(full_text)
        active_color   = "rgba(0,212,255,180)"
        inactive_color = "#1a2035"
        blocks = ""
        for i in range(5):
            color = active_color if i < level else inactive_color
            blocks += f'<span style="color:{color};">█</span>'
        self._conf_lbl.setText(f'<span style="color:#2a4060;">CONF: </span>{blocks}')
        self._conf_lbl.setTextFormat(Qt.RichText)
        self._conf_lbl.show()


# ── Área de chat com bolhas ─────────────────────────────────────
class ChatWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QLabel("◈ TERMINAL DE COMUNICAÇÃO — NERV HQ")
        header.setFont(QFont("Consolas", 8, QFont.Bold))
        header.setStyleSheet("""
            color: #00d4ff;
            background: #0a0d14;
            padding: 6px 12px;
            letter-spacing: 2px;
            border-bottom: 1px solid #1a2035;
        """)
        layout.addWidget(header)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: #070910; border: none; }
            QScrollBar:vertical {
                background: #0a0d14; width: 5px; border: none;
            }
            QScrollBar::handle:vertical {
                background: #1a2035; border-radius: 2px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self._container = QWidget()
        self._container.setStyleSheet("background: #070910;")
        self._bubbles_layout = QVBoxLayout(self._container)
        self._bubbles_layout.setContentsMargins(0, 8, 0, 8)
        self._bubbles_layout.setSpacing(1)
        self._bubbles_layout.addStretch()
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, stretch=1)

        self._current_bubble: MessageBubble | None = None
        self._current_ai_text = ""
        self._ai_thinking = False
        # MUDANÇA 2: referência ao skeleton atual
        self._skeleton: SkeletonBubble | None = None

        bus.on_user_message.connect(self._on_user_msg)
        bus.on_ai_token.connect(self._on_token)
        bus.on_ai_response.connect(self._on_ai_done)

    def _add_bubble(self, bubble: QWidget):
        count = self._bubbles_layout.count()
        self._bubbles_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _remove_skeleton(self):
        if self._skeleton is not None:
            self._skeleton.stop()
            self._skeleton.setParent(None)
            self._skeleton.deleteLater()
            self._skeleton = None

    def _limpar_para_ui(self, txt: str) -> str:
        # Remove pensamentos entre parênteses no início: "(Após 0,7 segundos...)"
        txt = re.sub(r'^\s*(\([^)]*\)\s*)+', '', txt)
        txt = re.sub(r'FONTES?:\s*\[.*', '', txt, flags=re.DOTALL | re.IGNORECASE)
        txt = re.sub(r'\[\d+\]', '', txt)
        txt = re.sub(r'\[(?:CASPER-3|MELCHIOR-1|BALTHASAR-2|ADAM-0)[^\]]*\]', '', txt)
        txt = re.sub(r'→\s*Analisando[^\n]*\n?', '', txt)
        txt = re.sub(r'─+', '', txt)
        txt = re.sub(r'\n{3,}', '\n\n', txt)
        return txt.strip()

    def _on_user_msg(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        bubble = MessageBubble("user", text, ts)
        self._add_bubble(bubble)

        # Cria bolha vazia para AI
        self._current_bubble = MessageBubble("ai", "", ts)
        self._add_bubble(self._current_bubble)
        self._current_ai_text = ""
        self._ai_thinking = True

        # MUDANÇA 2: insere skeleton antes da bolha AI
        self._skeleton = SkeletonBubble()
        self._add_bubble(self._skeleton)

    def _on_token(self, token: str):
        if self._ai_thinking:
            self._ai_thinking = False
            # Remove skeleton quando chegar primeiro token
            self._remove_skeleton()
        if self._current_bubble:
            self._current_bubble.append_text(token)
            self._current_ai_text += token
            QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ))

    def _on_ai_done(self, full_response: str):
        self._ai_thinking = False
        self._remove_skeleton()
        if self._current_bubble and not self._current_ai_text.strip():
            limpa = self._limpar_para_ui(full_response)
            self._current_bubble.set_text(limpa)
        # MUDANÇA 6: mostra confidence indicator
        if self._current_bubble:
            texto_final = self._current_ai_text.strip() or full_response
            self._current_bubble.show_confidence(texto_final)
        self._current_bubble = None
        self._current_ai_text = ""
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))


# ══════════════════════════════════════════════════════════════
# MUDANÇA 4 — InputWidget expansível com QTextEdit
# ══════════════════════════════════════════════════════════════
class _ExpandingInput(QTextEdit):
    """QTextEdit que envia com Enter e quebra linha com Shift+Enter."""
    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self):
        doc_h = int(self.document().size().height()) + 12
        h = max(40, min(doc_h, 120))
        self.setFixedHeight(h)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)  # newline
            else:
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)


class InputWidget(QWidget):
    message_sent = Signal(str)

    def __init__(self):
        super().__init__()
        # Não tem mais setFixedHeight — height dinâmica
        self.setMinimumHeight(52)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Prefixo
        prefix = QLabel("NERV >>")
        prefix.setFont(QFont("Consolas", 10, QFont.Bold))
        prefix.setStyleSheet("color: #c8001a;")
        prefix.setAlignment(Qt.AlignTop)
        layout.addWidget(prefix)

        # Input expansível
        self._input = _ExpandingInput()
        self._input.setFont(QFont("Consolas", 10))
        self._input.setPlaceholderText("Digite um comando ou pergunta... (Shift+Enter para nova linha)")
        self._input.setStyleSheet("""
            QTextEdit {
                background: #0a0d14;
                color: #e8eaf0;
                border: 1px solid #1a2035;
                border-radius: 0px;
                padding: 6px 10px;
            }
            QTextEdit:focus {
                border: 1px solid #c8001a;
            }
            QScrollBar { width: 0px; }
        """)
        self._input.send_requested.connect(self._send)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        # Contador de caracteres
        self._char_counter = QLabel("0 / 500")
        self._char_counter.setFont(QFont("Consolas", 8))
        self._char_counter.setStyleSheet("color: #2a4060;")
        self._char_counter.setFixedWidth(52)
        self._char_counter.setAlignment(Qt.AlignRight | Qt.AlignTop)
        layout.addWidget(self._char_counter)

        # Botão enviar
        btn = QPushButton("▶ ENVIAR")
        btn.setFont(QFont("Consolas", 9, QFont.Bold))
        btn.setFixedWidth(90)
        btn.setFixedHeight(34)
        btn.setStyleSheet("""
            QPushButton {
                background: #0d1e30;
                color: #00d4ff;
                border: 1px solid #00d4ff;
                border-radius: 0px;
            }
            QPushButton:hover {
                background: #0a2a40;
                border-color: #00eeff;
                color: #00eeff;
            }
            QPushButton:pressed {
                background: #001a28;
            }
        """)
        btn.clicked.connect(self._send)
        layout.addWidget(btn)

    def _on_text_changed(self):
        n = len(self._input.toPlainText())
        self._char_counter.setText(f"{n} / 500")
        self._char_counter.setStyleSheet(
            "color: #c8001a;" if n > 400 else "color: #2a4060;"
        )

    def _send(self):
        text = self._input.toPlainText().strip()
        if text:
            self.message_sent.emit(text)
            self._input.clear()

    def focus(self):
        self._input.setFocus()


# ── Log de eventos ao vivo ─────────────────────────────────────
class EventLogWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(120)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("◈ EVENT LOG")
        header.setFont(QFont("Consolas", 8, QFont.Bold))
        header.setStyleSheet("color: #c8001a; background: #0a0d14; padding: 4px 10px; letter-spacing: 2px; border-bottom: 1px solid #1a2035;")
        layout.addWidget(header)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 8))
        self._log.setStyleSheet("""
            QTextEdit {
                background: #070910;
                color: #3a6080;
                border: none;
                padding: 4px 10px;
            }
            QScrollBar:vertical { width: 4px; background: #0a0d14; border: none; }
            QScrollBar::handle:vertical { background: #1a2035; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout.addWidget(self._log)
        self._entries = deque(maxlen=100)

    def add(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {"INFO": "#3a8080", "OK": "#00ff88", "WARN": "#ffd60a", "ERROR": "#c8001a"}
        color  = colors.get(level, "#3a6080")
        self._entries.append((ts, level, msg, color))

        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#3a5060"))
        cursor.insertText(f"[{ts}] ", fmt)
        fmt.setForeground(QColor(color))
        cursor.insertText(f"[{level}] ", fmt)
        fmt.setForeground(QColor("#4a6070"))
        cursor.insertText(msg + "\n", fmt)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()


# ══════════════════════════════════════════════════════════════
# MUDANÇA 3 — AgentActivityWidget
# ══════════════════════════════════════════════════════════════
class AgentActivityWidget(QWidget):
    """Painel separado que mostra só a atividade do agente em tempo real."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("◈ ATIVIDADE DO AGENTE")
        header.setFont(QFont("Consolas", 8, QFont.Bold))
        header.setStyleSheet(
            "color: #e85d04; background: #0a0d14; padding: 4px 10px; "
            "letter-spacing: 2px; border-bottom: 1px solid #1a2035;"
        )
        layout.addWidget(header)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 8))
        self._log.setStyleSheet("""
            QTextEdit {
                background: #070910;
                color: #5a7090;
                border: none;
                padding: 4px 10px;
            }
            QScrollBar:vertical { width: 4px; background: #0a0d14; border: none; }
            QScrollBar::handle:vertical { background: #1a2035; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout.addWidget(self._log)

        bus.on_user_message.connect(self._on_user)
        bus.on_ai_response.connect(self._on_done)
        bus.on_ai_token.connect(self._on_token_received)
        self._receiving = False

    def _append(self, icon: str, msg: str, color: str = "#5a8090"):
        ts = datetime.now().strftime("%H:%M:%S")
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#2a4050"))
        cursor.insertText(f"[{ts}] ", fmt)
        fmt.setForeground(QColor(color))
        cursor.insertText(f"{icon} {msg}\n", fmt)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def _on_user(self, text: str):
        self._receiving = False
        self._append("→", f"ANALISANDO: {text[:35]}...", "#e85d04")
        QTimer.singleShot(400, lambda: self._append("→", "SINTETIZANDO...", "#ffd60a"))

    def _on_token_received(self, _):
        if not self._receiving:
            self._receiving = True

    def _on_done(self, _):
        self._receiving = False
        self._append("✓", "CONCLUÍDO", "#00ff88")


# ══════════════════════════════════════════════════════════════
# MUDANÇA 7 — AnimatedButton com microinterações físicas
# ══════════════════════════════════════════════════════════════
class AnimatedButton(QPushButton):
    """QPushButton com animação de press e hover."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._press_anim  = QPropertyAnimation(self, b"maximumHeight")
        self._press_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._press_anim.setDuration(120)

        self._hover_anim  = QPropertyAnimation(self, b"minimumHeight")
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._hover_anim.setDuration(80)

    def mousePressEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(32)
        self._press_anim.setEndValue(28)
        self._press_anim.finished.connect(self._bounce_back)
        self._press_anim.start()
        super().mousePressEvent(event)

    def _bounce_back(self):
        try:
            self._press_anim.finished.disconnect(self._bounce_back)
        except RuntimeError:
            pass
        self._press_anim.setStartValue(28)
        self._press_anim.setEndValue(32)
        self._press_anim.start()

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self.minimumHeight())
        self._hover_anim.setEndValue(34)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self.minimumHeight())
        self._hover_anim.setEndValue(32)
        self._hover_anim.start()
        super().leaveEvent(event)


# ══════════════════════════════════════════════════════════════
# FIX — Histórico de conversa persistente na UI
# ══════════════════════════════════════════════════════════════
class ConversationHistory:
    """
    Mantém o histórico completo de turnos (user + ai) da sessão.
    Usado para injetar contexto quando o MAGI não tem acesso ao
    histórico de suas próprias respostas sintetizadas pela UI.
    """
    MAX_TURNS = 20  # turnos (par user+ai) mantidos em memória

    def __init__(self):
        self._turns: list[dict] = []   # [{"user": ..., "ai": ...}, ...]
        self._current_user: str = ""

    def record_user(self, text: str):
        self._current_user = text

    def record_ai(self, text: str):
        if self._current_user:
            self._turns.append({"user": self._current_user, "ai": text})
            self._current_user = ""
            if len(self._turns) > self.MAX_TURNS:
                self._turns.pop(0)

    def last_ai(self) -> str:
        """Retorna a última resposta do agente, ou vazio."""
        if self._turns:
            return self._turns[-1]["ai"]
        return ""

    def context_block(self, n_turns: int = 6) -> str:
        """
        Retorna um bloco de texto com os últimos n_turns formatados
        para ser injetado antes do prompt do usuário.
        """
        if not self._turns:
            return ""
        recentes = self._turns[-n_turns:]
        linhas = ["[HISTÓRICO DA CONVERSA ATUAL — USE PARA DAR CONTINUIDADE]"]
        for i, t in enumerate(recentes, 1):
            linhas.append(f"Usuário: {t['user']}")
            linhas.append(f"NYTHERA: {t['ai']}")
            linhas.append("")
        linhas.append("[FIM DO HISTÓRICO]")
        return "\n".join(linhas)

    def needs_context(self, text: str) -> bool:
        """
        Detecta se o usuário está pedindo continuidade, repetição
        ou referenciando algo dito antes — sinaliza para injetar contexto.
        """
        if not self._turns:
            return False
        gatilhos = [
            "continua", "continue", "repete", "repita", "repita isso",
            "o que você disse", "você disse", "disse antes", "o que falou",
            "mais detalhes", "explique melhor", "pode explicar",
            "me fale mais", "fale mais", "me conte mais", "conte mais",
            "mais sobre isso", "sobre isso", "elabore", "aprofunde",
            "e daí", "e depois", "e então", "como assim", "qual era",
            "qual foi", "o que era", "o que foi", "lembra", "lembrar",
            "última resposta", "última vez", "de novo", "novamente",
        ]
        t = text.lower().strip()
        return any(g in t for g in gatilhos) or len(t) < 15


# ── Worker que integra com MAGISystem ──────────────────────────
class MAGIWorker(QThread):
    token_ready    = Signal(str)
    response_ready = Signal(str)
    status_update  = Signal(dict)
    module_update  = Signal(str, bool)

    @staticmethod
    def _limpar_resposta(txt: str) -> str:
        """Remove pensamentos entre parênteses no início da resposta."""
        return re.sub(r'^\s*(\([^)]*\)\s*)+', '', txt).strip()

    def __init__(self, magi=None):
        super().__init__()
        self.magi = magi
        self._queue = queue.Queue()
        self.history = ConversationHistory()   # ← histórico da sessão

    def send(self, text: str):
        self._queue.put(text)

    def run(self):
        while True:
            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Registra o turno do usuário antes de processar
            self.history.record_user(text)

            # Monta prompt enriquecido se precisar de contexto
            prompt = self._enriquecer_prompt(text)

            if self.magi:
                try:
                    self._processar_com_captura(prompt, original_text=text)
                except Exception as e:
                    self.response_ready.emit(f"[ERRO] {e}")
            else:
                # Modo demo — simula continuidade
                ultimo = self.history.last_ai()
                if self.history.needs_context(text) and ultimo:
                    demo = f"Continuando o que eu disse: \"{ultimo[:80]}...\" — posso elaborar mais sobre esse ponto."
                else:
                    demo = f"Sistema NYTHERA operacional. Você disse: '{text}'"
                for ch in demo:
                    self.token_ready.emit(ch)
                    time.sleep(0.015)
                self.response_ready.emit(demo)
                self.history.record_ai(demo)

    def _enriquecer_prompt(self, text: str) -> str:
        """
        Se o usuário está pedindo continuidade/referência, injeta o
        histórico recente antes do texto para o MAGI ter contexto.
        """
        if self.history.needs_context(text):
            ctx = self.history.context_block(n_turns=5)
            if ctx:
                return f"{ctx}\n\nUsuário agora diz: {text}"
        return text

    def _processar_com_captura(self, text: str, original_text: str = ""):
        import threading as _th

        capturada  = []          # resposta final completa
        done       = _th.Event()
        original_nucleo = self.magi._chamar_nucleo

        # ── Stream real: tokens chegam direto da API DeepSeek ──────────────
        def _on_stream_token(token: str):
            self.token_ready.emit(token)

        self.magi._stream_callback = _on_stream_token

        # ── Callback para _responder_conversa (streaming já ativo lá também) ──
        def _callback_conversa(r: str):
            if r:
                capturada.append(self._limpar_resposta(r))

        self.magi._resposta_callback = _callback_conversa

        # ── Hook de nucleo: captura resultado final + fallback sem streaming ──
        def _hook_nucleo(nome: str, prompt: str):
            r, mod = original_nucleo(nome, prompt)
            if nome == "CASPER-3" and r:
                r_limpo = self._limpar_resposta(r)
                capturada.append(r_limpo)
                # Se não houve streaming (fallback local/openai), simula animação
                if not self.magi._stream_callback:
                    words = r_limpo.split()
                    for i, w in enumerate(words):
                        sep = " " if i < len(words) - 1 else ""
                        self.token_ready.emit(w + sep)
                        time.sleep(0.02)
            return r, mod

        def _processar():
            try:
                self.magi._chamar_nucleo = _hook_nucleo
                self.magi.processar(text)
            except Exception as e:
                self.response_ready.emit(f"[ERRO] {e}")
            finally:
                self.magi._chamar_nucleo   = original_nucleo
                self.magi._stream_callback  = None
                self.magi._resposta_callback = None
                done.set()

        t = _th.Thread(target=_processar, daemon=True)
        t.start()
        done.wait(timeout=120)

        if capturada:
            resposta = capturada[-1]
            self.response_ready.emit(resposta)
            self.history.record_ai(resposta)
            self._emitir_status()
            return

        hist_antes = len(self.magi.historico) if hasattr(self.magi, "historico") else 0
        for _ in range(50):
            if hasattr(self.magi, "historico") and len(self.magi.historico) > hist_antes:
                ultimo = list(self.magi.historico)[-1]
                for sep in ("| CASPER:", "CASPER:", "|"):
                    if sep in ultimo:
                        resposta = ultimo.split(sep)[-1].strip()
                        self.response_ready.emit(resposta)
                        self.history.record_ai(resposta)
                        self._emitir_status()
                        return
                resposta = ultimo.strip()
                self.response_ready.emit(resposta)
                self.history.record_ai(resposta)            # ← registra
                self._emitir_status()
                return
            time.sleep(0.1)

        self.response_ready.emit("[Sem resposta — confira o terminal]")

    def _emitir_status(self):
        try:
            estado = self.magi.consciencia._estado
            self.status_update.emit({
                "ESTADO":  estado.get("emocao", "curioso"),
                "SESSÃO":  f"{estado.get('total_queries', 0)} queries",
                "MEMÓRIA": f"{len(self.magi.memoria.registros)} registros",
                "MODELO":  getattr(self.magi, "_ultimo_modelo_usado", "deepseek-chat"),
            })
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# MUDANÇA 5 — GlassPanel com glassmorphism
# ══════════════════════════════════════════════════════════════
class GlassPanel(QWidget):
    """Widget com efeito glassmorphism sutil para painéis laterais."""

    def __init__(self, side: str = "left", parent=None):
        super().__init__(parent)
        self._side = side  # "left" ou "right"
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Base semi-opaca
        base = QColor(10, 13, 20, 200)
        p.fillRect(self.rect(), base)

        # Gradiente vertical cyan sutil no topo
        grd = QLinearGradient(0, 0, 0, self.height())
        grd.setColorAt(0.0, QColor(0, 212, 255, 8))
        grd.setColorAt(0.35, QColor(0, 212, 255, 3))
        grd.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(grd))

        # Borda interna (direita para painel esquerdo, esquerda para direito)
        border_color = QColor(0, 212, 255, 18)
        p.setPen(QPen(border_color, 1))
        if self._side == "left":
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        else:
            p.drawLine(0, 0, 0, self.height())

        p.end()


# ── Janela principal ───────────────────────────────────────────
class MAGIWindow(QMainWindow):
    def __init__(self, magi=None):
        super().__init__()
        self.setWindowTitle("NYTHERA — MAGI SYSTEM")
        self.setMinimumSize(1200, 720)
        self.resize(1400, 820)
        self._apply_global_style()

        self._worker = MAGIWorker(magi)
        self._worker.token_ready.connect(bus.on_ai_token)
        self._worker.response_ready.connect(bus.on_ai_response)
        self._worker.status_update.connect(bus.on_status_update)
        self._worker.start()

        self._event_log = EventLogWidget()
        self._event_log.add("OK", "NYTHERA SYSTEM ONLINE")
        self._event_log.add("OK", "Todos os núcleos ativos")
        self._event_log.add("INFO", "Aguardando entrada do operador")

        self._build_ui()
        self._connect_signals()

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #070910;
                color: #c8d0e0;
            }
            QFrame[frameShape="4"] { color: #1a2035; }
            QSplitter::handle { background: #1a2035; width: 1px; height: 1px; }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        topbar = self._make_topbar()
        root.addWidget(topbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #c8001a; background: #c8001a;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        left = self._make_left_panel()
        body.addWidget(left)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #1a2035; background: #1a2035;")
        sep2.setFixedWidth(1)
        body.addWidget(sep2)

        center = self._make_center()
        body.addWidget(center, stretch=1)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("color: #1a2035; background: #1a2035;")
        sep3.setFixedWidth(1)
        body.addWidget(sep3)

        right = self._make_right_panel()
        body.addWidget(right)

        root.addLayout(body, stretch=1)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.HLine)
        sep4.setStyleSheet("color: #1a2035; background: #1a2035;")
        sep4.setFixedHeight(1)
        root.addWidget(sep4)

        bottom = self._make_bottom()
        root.addWidget(bottom)

    def _make_topbar(self):
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background: #0a0d14; border-bottom: 1px solid #1a2035;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        logo = QLabel("NYTHERA // MAGI SYSTEM")
        logo.setFont(QFont("Consolas", 12, QFont.Bold))
        logo.setStyleSheet("""
            color: #c8001a;
            letter-spacing: 3px;
        """)
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(18)
        glow.setColor(QColor("#c8001a"))
        glow.setOffset(0, 0)
        logo.setGraphicsEffect(glow)
        layout.addWidget(logo)

        layout.addStretch()

        ts_label = QLabel()
        ts_label.setFont(QFont("Consolas", 8))
        ts_label.setStyleSheet("color: #ffd60a; letter-spacing: 1px;")
        layout.addWidget(ts_label)

        self._online_dot = QLabel("●")
        self._online_dot.setFont(QFont("Consolas", 11, QFont.Bold))
        self._online_dot.setStyleSheet("color: #00ff88; margin-left: 8px;")
        online_lbl = QLabel("ONLINE")
        online_lbl.setFont(QFont("Consolas", 9, QFont.Bold))
        online_lbl.setStyleSheet("color: #00ff88; margin-right: 4px;")
        layout.addWidget(self._online_dot)
        layout.addWidget(online_lbl)

        self._pulse_state = True
        t = QTimer(bar)
        def _upd():
            ts_label.setText(datetime.now().strftime("  %Y.%m.%d  %H:%M:%S  "))
            self._pulse_state = not self._pulse_state
            self._online_dot.setStyleSheet(
                "color: #00ff88; margin-left: 8px;" if self._pulse_state
                else "color: #004422; margin-left: 8px;"
            )
        t.timeout.connect(_upd)
        t.start(900)
        _upd()
        return bar

    def _make_left_panel(self):
        # MUDANÇA 5: usa GlassPanel
        panel = GlassPanel(side="left")
        panel.setFixedWidth(240)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        orb_container = QWidget()
        orb_container.setStyleSheet("background: transparent;")
        orb_layout = QVBoxLayout(orb_container)
        orb_layout.setContentsMargins(0, 12, 0, 8)
        orb_layout.setAlignment(Qt.AlignCenter)
        self._orb = OrbWidget()
        orb_layout.addWidget(self._orb, alignment=Qt.AlignCenter)
        layout.addWidget(orb_container)

        self._eq = EqualizerWidget()
        layout.addWidget(self._eq)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2035; background: #1a2035;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._modules = ModuleStatusWidget()
        layout.addWidget(self._modules)

        return panel

    def _make_center(self):
        panel = QWidget()
        panel.setStyleSheet("background: #070910;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._chat = ChatWidget()
        layout.addWidget(self._chat, stretch=1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2035; background: #1a2035;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        layout.addWidget(self._event_log)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #c8001a; background: #c8001a;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        self._input = InputWidget()
        layout.addWidget(self._input)

        return panel

    def _make_right_panel(self):
        # MUDANÇA 5: usa GlassPanel
        panel = GlassPanel(side="right")
        panel.setFixedWidth(240)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status = StatusPanel()
        layout.addWidget(self._status)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1a2035; background: #1a2035;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # MUDANÇA 3: AgentActivityWidget
        self._activity = AgentActivityWidget()
        layout.addWidget(self._activity)

        # Separador vermelho entre activity e event log
        sep_red = QFrame()
        sep_red.setFrameShape(QFrame.HLine)
        sep_red.setStyleSheet("color: #c8001a; background: #c8001a;")
        sep_red.setFixedHeight(1)
        layout.addWidget(sep_red)

        # Ações rápidas
        actions_label = QLabel("◈ AÇÕES RÁPIDAS")
        actions_label.setFont(QFont("Consolas", 8, QFont.Bold))
        actions_label.setStyleSheet("color: #00d4ff; padding: 8px 8px 4px; letter-spacing: 2px;")
        layout.addWidget(actions_label)

        actions = [
            ("⬡  DIAGNÓSTICO",  "diagnostico", "#00d4ff"),
            ("◎  VOZ ON/OFF",   "voz",          "#00ff88"),
            ("✕  LIMPAR",       "limpar",        "#c8001a"),
            ("◈  EGO",          "ego",           "#aa44ff"),
            ("⊞  MEMÓRIA",      "memoria",       "#ffd60a"),
            ("⚔  DEBATE",       "debate",        "#e85d04"),
        ]
        for label, cmd, hover_color in actions:
            # MUDANÇA 7: AnimatedButton
            btn = AnimatedButton(label)
            btn.setFont(QFont("Consolas", 8))
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #0d1018;
                    color: #4a7090;
                    border: 1px solid #1a2035;
                    border-left: 2px solid #1a2035;
                    border-radius: 0;
                    text-align: left;
                    padding-left: 12px;
                }}
                QPushButton:hover {{
                    background: #0d1828;
                    color: {hover_color};
                    border-color: {hover_color};
                    border-left: 2px solid {hover_color};
                }}
            """)
            btn.clicked.connect(lambda checked, c=cmd: self._quick_action(c))
            layout.addWidget(btn)

        # Botão mute
        self._btn_mute = AnimatedButton("🎤 MICROFONE: ATIVO")
        self._btn_mute.setFont(QFont("Consolas", 8))
        self._btn_mute.setFixedHeight(32)
        self._btn_mute.setCheckable(True)
        self._btn_mute.setStyleSheet("""
            QPushButton {
                background: #0d1a0d;
                color: #00ff88;
                border: 1px solid #00ff88;
                border-radius: 0;
                padding-left: 12px;
                text-align: left;
            }
            QPushButton:checked {
                background: #1a0d0d;
                color: #c8001a;
                border-color: #c8001a;
            }
            QPushButton:hover { opacity: 0.8; }
        """)
        self._btn_mute.clicked.connect(self._toggle_mute)
        layout.addWidget(self._btn_mute)

        layout.addStretch()
        return panel

    def _make_bottom(self):
        bar = QWidget()
        bar.setFixedHeight(24)
        bar.setStyleSheet("background: #0a0d14; border-top: 1px solid #0d1018;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)

        left = QLabel("NERV HQ  //  MAGI COMPUTATIONAL SYSTEM  //  CLASSIFIED LEVEL 4")
        left.setFont(QFont("Consolas", 7))
        left.setStyleSheet("color: #2a3545; letter-spacing: 1px;")
        layout.addWidget(left)

        layout.addStretch()

        self._model_bar = QLabel(
            "MELCHIOR: DEEPSEEK V3  ·  BALTHASAR: DEEPSEEK V3  ·  CASPER: DEEPSEEK V3  ·  ADAM-0: DEEPSEEK V3"
        )
        self._model_bar.setFont(QFont("Consolas", 7))
        self._model_bar.setStyleSheet("color: #1a3040; letter-spacing: 1px;")
        self._model_bar.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._model_bar)

        layout.addStretch()

        right = QLabel(f"BUILD {datetime.now().strftime('%Y%m%d')}")
        right.setFont(QFont("Consolas", 7))
        right.setStyleSheet("color: #2a3545; letter-spacing: 1px;")
        layout.addWidget(right)

        def _on_modelo(data: dict):
            if "MODELO" in data:
                m = data["MODELO"]
                self._model_bar.setText(
                    f"MELCHIOR: {m}  ·  BALTHASAR: {m}  ·  CASPER: {m}  ·  ADAM-0: {m}"
                )
        bus.on_status_update.connect(_on_modelo)

        return bar

    def _connect_signals(self):
        self._input.message_sent.connect(self._on_send)
        bus.on_ai_response.connect(lambda _: self._event_log.add("OK", "Resposta gerada"))
        bus.on_user_message.connect(lambda t: self._event_log.add("INFO", f"Input: {t[:40]}"))
        # Garante que respostas via bus (modo demo) também entram no histórico
        bus.on_ai_response.connect(self._worker.history.record_ai)

    def _on_send(self, text: str):
        bus.on_user_message.emit(text)
        self._worker.send(text)
        needs_ctx = self._worker.history.needs_context(text)
        suffix = " [+contexto]" if needs_ctx else ""
        self._event_log.add("INFO", f"Processando{suffix}: {text[:28]}...")

    def _quick_action(self, cmd: str):
        self._input._input.setPlainText(cmd)
        self._on_send(cmd)
        self._input._input.clear()

    def _toggle_mute(self):
        magi = self._worker.magi
        if not magi:
            self._event_log.add("WARN", "Sistema de voz não está ativo.")
            self._btn_mute.setChecked(False)
            return

        # Inicializa voz com o histórico compartilhado se ainda não existir
        if not hasattr(magi, 'voz') or not magi.voz:
            try:
                from magi_voz import integrar_voz_ao_magi
                integrar_voz_ao_magi(magi, history=self._worker.history)
                magi.voz.iniciar()
                self._event_log.add("OK", "Sistema de voz iniciado com histórico compartilhado.")
            except ImportError:
                self._event_log.add("ERROR", "magi_voz.py não encontrado.")
                self._btn_mute.setChecked(False)
                return
            except Exception as e:
                self._event_log.add("ERROR", f"Voz: {e}")
                self._btn_mute.setChecked(False)
                return

        # Garante que o history da voz está sincronizado
        if hasattr(magi.voz, '_history') and magi.voz._history is None:
            magi.voz._history = self._worker.history

        if magi.voz._mutado:
            magi.voz.desmutar()
            self._btn_mute.setText("🎤 MICROFONE: ATIVO")
            self._btn_mute.setChecked(False)
            self._event_log.add("OK", "Microfone reativado.")
        else:
            magi.voz.mutar()
            self._btn_mute.setText("🔇 MICROFONE: MUTADO")
            self._btn_mute.setChecked(True)
            self._event_log.add("WARN", "Microfone mutado.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


# ── Integração com MAGISystem ──────────────────────────────────
def iniciar_ui(magi=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor("#070910"))
    pal.setColor(QPalette.WindowText, QColor("#c8d0e0"))
    app.setPalette(pal)
    win = MAGIWindow(magi)
    win.show()
    return app, win


if __name__ == "__main__":
    app, win = iniciar_ui(magi=None)
    sys.exit(app.exec())