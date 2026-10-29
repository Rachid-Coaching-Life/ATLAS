"""Lightweight projected HUD, attached to ATLAS's existing floating face.

Pure Qt painting: no WebEngine, network access, secondary window or new assets.
The tray forwards public, visible daemon-log lines on Qt's GUI thread.
"""

from __future__ import annotations

import math
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


_STATE_TEXT = {
    "asleep": "HORS LIGNE",
    "idle": "À VOTRE SERVICE",
    "listening": "EN ÉCOUTE",
    "thinking": "ANALYSE EN COURS",
    "speaking": "ATLAS VOUS RÉPOND",
    "dictating": "DICTÉE EN COURS",
    "dictation_processing": "TRAITEMENT DE LA DICTÉE",
}


class HologramPanel(QWidget):
    """HUD that displays genuine listening state, heard speech and replies."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("atlas_hologram")
        self.setMinimumWidth(210)
        self.setMinimumHeight(190)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._state = "asleep"
        self._phase_origin = time.monotonic()
        self._await_reply_line = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(23, 22, 23, 21)
        outer.setSpacing(9)

        self.heading = QLabel("ATLAS  /  INTERFACE NEURALE")
        self.heading.setObjectName("atlas_hud_heading")
        self.heading.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.heading.setStyleSheet("color: #66d8ff; letter-spacing: 2px;")
        outer.addWidget(self.heading)

        self.status = QLabel(_STATE_TEXT[self._state])
        self.status.setObjectName("atlas_hud_status")
        self.status.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self.status.setStyleSheet("color: #ffaf66;")
        outer.addWidget(self.status)

        self._label(outer, "DERNIÈRE DEMANDE")
        self.heard = self._message("Prononcez « Atlas » pour commencer.")
        self.heard.setObjectName("atlas_hud_heard")
        outer.addWidget(self.heard)

        self._label(outer, "RÉPONSE")
        self.reply = self._message("Prêt à vous accompagner.")
        self.reply.setObjectName("atlas_hud_reply")
        outer.addWidget(self.reply)

        outer.addStretch(1)
        self.footer = QLabel("●   AUDIO LOCAL  ·  ASSISTANT PERSONNEL")
        self.footer.setStyleSheet("color: #678ca1; font-size: 9px;")
        outer.addWidget(self.footer)

        self._timer = QTimer(self)
        self._timer.setInterval(85)
        self._timer.timeout.connect(self.update)

    @staticmethod
    def _label(layout, value):
        label = QLabel(value)
        label.setStyleSheet("color: #75a7bc; font-size: 9px; letter-spacing: 1px;")
        layout.addWidget(label)

    @staticmethod
    def _message(value):
        label = QLabel(value)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setStyleSheet("color: #e5f6ff; font-size: 12px;")
        label.setMaximumHeight(62)
        return label

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def set_activity(self, state: str) -> None:
        self._state = state
        self.status.setText(_STATE_TEXT.get(state, "ATLAS ACTIF"))
        active = state in {"speaking", "listening", "thinking", "dictating"}
        self.status.setStyleSheet("color: #56d9ff;" if active else "color: #ffaf66;")
        self.update()

    def ingest_log(self, line: str) -> None:
        """Show only visible conversation lines, never raw IPC or diagnostics."""
        if not isinstance(line, str):
            return
        for part in line.splitlines():
            stripped = part.strip()
            if stripped.startswith("📝 Heard:"):
                heard = stripped.split("Heard:", 1)[1].strip().strip('"')
                if heard:
                    self.heard.setText(heard[:230])
                self._await_reply_line = False
            elif "🤖 ATLAS" in stripped or "⚠️ ATLAS" in stripped:
                self._await_reply_line = True
            elif self._await_reply_line and stripped:
                # The reply logger prints the text on the following line.
                # Avoid treating another event heading as a reply.
                if not stripped.startswith(("⏱️", "📝", "🔧", "🔁", "✨", "─")):
                    self.reply.setText(stripped[:250])
                self._await_reply_line = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(4, 4, -4, -4)
        if bounds.width() <= 0 or bounds.height() <= 0:
            return
        bg = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        bg.setColorAt(0, QColor(5, 21, 35, 232))
        bg.setColorAt(.5, QColor(6, 16, 29, 220))
        bg.setColorAt(1, QColor(7, 18, 30, 232))
        painter.setPen(QPen(QColor(30, 139, 179, 140), 1.2))
        painter.setBrush(bg)
        painter.drawRoundedRect(bounds, 14, 14)

        t = time.monotonic() - self._phase_origin
        pulse = .57 + .25 * math.sin(t * 2.8)
        bright = QColor(50, 200, 255)
        bright.setAlphaF(pulse)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(bright, 2.0))
        x, y, w, h = bounds.x(), bounds.y(), bounds.width(), bounds.height()
        for points in (
            ((x + 7, y + 32), (x + 7, y + 7), (x + 48, y + 7)),
            ((x + w - 48, y + 7), (x + w - 7, y + 7), (x + w - 7, y + 32)),
            ((x + 7, y + h - 32), (x + 7, y + h - 7), (x + 48, y + h - 7)),
            ((x + w - 48, y + h - 7), (x + w - 7, y + h - 7),
             (x + w - 7, y + h - 32)),
        ):
            path = QPainterPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            painter.drawPath(path)
        painter.setPen(QPen(QColor(255, 153, 67, 190), 1))
        painter.drawLine(int(x + 20), int(y + 79), int(x + w - 20), int(y + 79))
        painter.end()


class ProjectionBridge(QWidget):
    """A luminous circuit physically connecting the panel to ATLAS's portrait."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(47)
        self.setMinimumHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._vertical = False
        self._state = "asleep"
        self._phase_origin = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(110)
        self._timer.timeout.connect(self.update)

    def set_vertical(self, vertical: bool) -> None:
        self._vertical = vertical
        if vertical:
            self.setMinimumWidth(0)
            self.setFixedHeight(30)
            self.setMaximumWidth(16777215)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setFixedWidth(47)
        self.updateGeometry()
        self.update()

    def set_activity(self, state: str) -> None:
        self._state = state
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self._state in {"listening", "thinking", "speaking", "dictating"}
        intensity = (.65 + .3 * math.sin((time.monotonic() - self._phase_origin) * 5)
                     if active else .3)
        cyan = QColor(49, 209, 255)
        cyan.setAlphaF(intensity)
        orange = QColor(255, 156, 70, 165)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(cyan, 2))
        w, h = self.width(), self.height()
        if self._vertical:
            x = w / 2
            painter.drawLine(int(x), 0, int(x), h)
            painter.setPen(QPen(orange, 1))
            painter.drawLine(int(x - 15), int(h / 2), int(x + 15), int(h / 2))
        else:
            mid = h / 2
            path = QPainterPath()
            path.moveTo(0, mid)
            path.lineTo(w * .38, mid)
            path.lineTo(w * .62, mid - 12)
            path.lineTo(w, mid - 12)
            painter.drawPath(path)
            painter.setPen(QPen(orange, 1))
            painter.drawLine(0, int(mid + 9), w, int(mid + 9))
        painter.end()
