"""Original sculptural hologram for ATLAS's unchanged floating portrait.

All visual effects are real-time Qt raster painting in the *existing* HUD and
connector widgets. No new surface, dependencies, background tasks or assets.
The face artwork, dimensions, geometry and lip animation are not altered.
"""
from __future__ import annotations

import math
import os
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient, QRadialGradient, QPainter, QPainterPath, QPen, QRegion,
)
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


_STATE_TEXT = {
    "asleep": "HORS LIGNE",
    "idle": "À VOTRE SERVICE",
    "listening": "EN ÉCOUTE",
    "thinking": "ANALYSE EN COURS",
    "speaking": "ATLAS VOUS RÉPOND",
    "dictating": "DICTÉE EN COURS",
    "dictation_processing": "TRAITEMENT DE LA DICTÉE",
}
_ACTIVE = frozenset({"listening", "thinking", "speaking", "dictating", "dictation_processing"})
_CYAN = QColor(59, 209, 255)
_AMBER = QColor(255, 159, 71)


def _glass_outline(width: float, height: float) -> QPainterPath:
    """Concave multi-faceted silhouette with cut-away corners and emitter notch.

    The path is expressed as fractions of the panel's allocated rectangle.
    Neither its outside corners nor its right-hand side form a rounded box.
    """
    w, h = float(width), float(height)
    if w <= 0 or h <= 0:
        return QPainterPath()
    path = QPainterPath(QPointF(.11 * w, .018 * h))
    path.lineTo(.58 * w, .018 * h)
    path.lineTo(.635 * w, .001 * h)
    path.lineTo(.81 * w, .001 * h)
    path.lineTo(.956 * w, .094 * h)
    path.lineTo(.956 * w, .266 * h)
    path.lineTo(.929 * w, .301 * h)
    path.lineTo(.929 * w, .418 * h)
    path.lineTo(.993 * w, .497 * h)
    path.lineTo(.929 * w, .559 * h)
    path.lineTo(.929 * w, .727 * h)
    path.lineTo(.964 * w, .759 * h)
    path.lineTo(.964 * w, .863 * h)
    path.lineTo(.825 * w, .985 * h)
    path.lineTo(.18 * w, .985 * h)
    path.lineTo(.115 * w, .935 * h)
    path.lineTo(.049 * w, .887 * h)
    path.lineTo(.049 * w, .668 * h)
    path.lineTo(.014 * w, .627 * h)
    path.lineTo(.044 * w, .545 * h)
    path.lineTo(.044 * w, .322 * h)
    path.lineTo(.077 * w, .267 * h)
    path.lineTo(.077 * w, .096 * h)
    path.closeSubpath()
    return path


def _facet(points: tuple[tuple[float, float], ...], w: float, h: float) -> QPainterPath:
    path = QPainterPath(QPointF(w * points[0][0], h * points[0][1]))
    for x, y in points[1:]:
        path.lineTo(w * x, h * y)
    path.closeSubpath()
    return path


class HologramPanel(QWidget):
    """One nonrectangular glass projection, with real activity and speech data."""

    voice_command_requested = pyqtSignal()
    exchange_view_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("atlas_hologram")
        self.setMinimumWidth(210)
        self.setMinimumHeight(190)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Unhandled pointer events bubble up to FaceWindow for drag and menu.
        # The two real control buttons must receive mouse events themselves.
        self._state = "asleep"
        # Opt-in low effects for offscreen profiling and future diagnostics.
        # Default visual geometry, text, controls and portrait are unchanged.
        self._low_effects = os.environ.get("ATLAS_HOLOGRAM_LOW_EFFECTS") == "1"
        # Opt-in CPU raster cache: preserve optical highlights without
        # redrawing gradients and micro-circuits on every live frame.
        self._cached_effects = os.environ.get("ATLAS_HOLOGRAM_CACHED_EFFECTS") == "1"
        # Experimental composition, deliberately restricted to the measured
        # low-cadence hybrid mode. Existing layout/text/buttons are untouched.
        self._sculpted = (
            os.environ.get("ATLAS_HOLOGRAM_SCULPTED") == "1"
            and self._cached_effects and self._low_effects
        )
        # One-time optical pane materials. This option requires the low-cost,
        # cached sculptural mode; the normal desktop HUD remains untouched.
        self._optical = (
            os.environ.get("ATLAS_HOLOGRAM_OPTICAL") == "1"
            and self._sculpted
        )
        self._optical_card_cache = {}
        self._spectral_cache = None
        self._spectral_cache_key = None
        self._phase_origin = time.monotonic()
        self._revealed_at = None
        self._await_reply_line = False

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(65, 21, 43, 23)
        self._outer.setSpacing(7)

        self.heading = QLabel("ATLAS  /  INTERFACE NEURALE")
        self.heading.setObjectName("atlas_hud_heading")
        self.heading.setWordWrap(True)
        self.heading.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.heading.setStyleSheet("color: #d9f7ff; letter-spacing: 1.1px;")
        self._outer.addWidget(self.heading)

        self.status = QLabel(_STATE_TEXT[self._state])
        self.status.setObjectName("atlas_hud_status")
        self.status.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.status.setStyleSheet("color: #ffbd69; letter-spacing: .6px;")
        self._outer.addWidget(self.status)

        self.heard_caption = self._label(self._outer, "DERNIÈRE DEMANDE")
        self.heard = self._message("Prononcez « Atlas » pour commencer.")
        self.heard.setObjectName("atlas_hud_heard")
        self._outer.addWidget(self.heard, 1)

        self.reply_caption = self._label(self._outer, "RÉPONSE")
        self.reply = self._message("Prêt à vous accompagner.")
        self.reply.setObjectName("atlas_hud_reply")
        self._outer.addWidget(self.reply, 1)

        self._outer.addStretch(1)
        self.controls = QHBoxLayout()
        self.controls.setContentsMargins(0, 0, 0, 0)
        self.controls.setSpacing(7)
        self.voice_button = self._control_button("ACTIVER VOIX", "atlas_hud_voice")
        self.voice_button.setAccessibleName("Commande d’activation vocale")
        self.voice_button.clicked.connect(
            lambda _checked=False: self.voice_command_requested.emit()
        )
        self.controls.addWidget(self.voice_button, 1)
        self.exchanges_button = self._control_button("ÉCHANGES", "atlas_hud_exchanges")
        self.exchanges_button.setAccessibleName("Afficher tous les échanges")
        self.exchanges_button.setToolTip("Ouvrir la conversation ATLAS")
        self.exchanges_button.clicked.connect(
            lambda _checked=False: self.exchange_view_requested.emit()
        )
        self.controls.addWidget(self.exchanges_button, 1)
        self._outer.addLayout(self.controls)

        self.footer = QLabel("◉  AUDIO LOCAL  ·  ASSISTANT PERSONNEL")
        self.footer.setObjectName("atlas_hud_footer")
        self.footer.setStyleSheet("color: #8bd5f5; font-size: 9px;")
        self._outer.addWidget(self.footer)
        self.set_voice_control(running=False)

        self._timer = QTimer(self)
        # Four visual refreshes per second by default, or two in diagnostic
        # low-effects mode. No perpetual updates in idle state.
        self._timer.setInterval(500 if self._low_effects else 250)
        self._timer.timeout.connect(self.update)

        # Real CPU/RAM in the existing optical telemetry crystal.
        # No separate process, GPU probe or paint-time system call.
        self._telemetry_cpu_pct = None
        self._telemetry_ram_pct = None
        self._telemetry_primed = False
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(3000)
        self._telemetry_timer.timeout.connect(self._refresh_live_telemetry)

    @staticmethod
    def _label(layout, value):
        label = QLabel(value)
        label.setStyleSheet("color: #65dfff; font-size: 11px; letter-spacing: .4px;")
        layout.addWidget(label)
        return label

    @staticmethod
    def _control_button(text: str, name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setMinimumWidth(0)
        button.setFixedHeight(25)
        button.setStyleSheet(
            "QPushButton { color: #d6f9ff; font: bold 9px 'Segoe UI';"
            " background: rgba(0, 59, 90, 147);"
            " border: 1px solid rgba(55, 204, 255, 165);"
            " border-bottom: 2px solid #21c9ff; padding: 2px 4px; }"
            "QPushButton:hover { color: #ffffff;"
            " background: rgba(18, 104, 141, 190); }"
            "QPushButton:pressed { color: #ffbb75; border-bottom-color: #ff9c36; }"
            "QPushButton:disabled { color: #7d9ead;"
            " border: 1px solid rgba(70, 121, 145, 105);"
            " background: rgba(4, 30, 45, 75); }"
        )
        return button

    @staticmethod
    def _message(value):
        label = QLabel(value)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setStyleSheet("color: #effcff; font-size: 13px;")
        label.setMaximumHeight(65)
        return label

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 295 or self.height() < 265
        # Keep all real text visible on 210px screens without expanding the
        # allocated window or changing the portrait's size/position.
        self._outer.setContentsMargins(
            29 if compact else (41 if self.width() < 390 else 65),
            18 if compact else 21,
            24 if compact else 43,
            16 if compact else 23,
        )
        self._outer.setSpacing(2 if compact else 7)
        self.footer.setVisible(not compact)
        self.controls.setSpacing(3 if compact else 7)
        font = self.heading.font()
        font.setPointSize(8 if compact else 11)
        self.heading.setFont(font)
        font = self.status.font()
        font.setPointSize(10 if compact else 14)
        self.status.setFont(font)
        for text in (self.heard, self.reply):
            text.setMaximumHeight(39 if compact else 65)
            # Reserve a proper instrument column for live mic/neural glyphs.
            text.setContentsMargins(0 if compact or self.width() < 390 else 43, 0, 0, 0)

    def set_voice_control(
        self, *, running: bool, paused: bool | None = False,
        pending: bool = False, available: bool = True,
    ) -> None:
        """Reflect confirmed daemon state, never optimistically claim success."""
        if not available:
            caption, hint, enabled = (
                "VOIX INDISP.", "Commande vocale momentanément indisponible", False
            )
        elif pending:
            caption, hint, enabled = (
                "VOIX EN COURS", "Changement de l’écoute vocale en cours", False
            )
        elif not running:
            caption, hint, enabled = (
                "ACTIVER VOIX", "Démarrer l’assistant vocal ATLAS", True
            )
        elif paused is None:
            caption, hint, enabled = (
                "VOIX INCONNUE", "État vocal non confirmé, réessayer", True
            )
        elif paused:
            caption, hint, enabled = (
                "REPRENDRE VOIX", "Reprendre l’écoute vocale", True
            )
        else:
            caption, hint, enabled = (
                "SUSPENDRE VOIX", "Suspendre l’écoute sans fermer le chat", True
            )
        self.voice_button.setText(caption)
        self.voice_button.setToolTip(hint)
        self.voice_button.setEnabled(enabled)

    def showEvent(self, event):
        super().showEvent(event)
        if self._optical:
            self._telemetry_primed = False
            self._refresh_live_telemetry()
            self._telemetry_timer.start()
        if self._state in _ACTIVE:
            self._revealed_at = time.monotonic()
            self._timer.start()
        else:
            self._revealed_at = None
            self._timer.stop()

    def hideEvent(self, event):
        self._timer.stop()
        self._telemetry_timer.stop()
        super().hideEvent(event)

    def _refresh_live_telemetry(self) -> None:
        """Read system CPU/RAM without blocking the Qt event loop.

        CPU is a mean since the previous sample; it is not temperature or
        electrical power. The first read establishes the baseline.
        """
        if not self._optical or not self.isVisible():
            return
        try:
            import psutil  # Existing ATLAS dependency.
            sample = psutil.cpu_percent(interval=None)
            cpu = float(sample) if self._telemetry_primed else None
            self._telemetry_primed = True
            ram = float(psutil.virtual_memory().percent)
            self._telemetry_cpu_pct = cpu
            self._telemetry_ram_pct = ram
        except Exception:
            self._telemetry_cpu_pct = None
            self._telemetry_ram_pct = None
        cpu_text = (
            f"{self._telemetry_cpu_pct:.0f} %"
            if self._telemetry_cpu_pct is not None else "indisponible"
        )
        ram_text = (
            f"{self._telemetry_ram_pct:.0f} %"
            if self._telemetry_ram_pct is not None else "indisponible"
        )
        self.setAccessibleDescription(
            f"Télémétrie système : CPU {cpu_text}, RAM {ram_text}"
        )
        self.update()

    def set_activity(self, state: str) -> None:
        self._state = state
        self.status.setText(_STATE_TEXT.get(state, "ATLAS ACTIF"))
        self.status.setStyleSheet(
            "color: #7fe3ff;" if state in _ACTIVE else "color: #ffc082;"
        )
        if state in _ACTIVE and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        # Repaint once on state change even when animation is suspended.
        self.update()

    def set_conversation_preview(self, request: str, response: str) -> None:
        """Reflect real text-chat turns in the same hologram as voice activity.

        Qt owns the labels and the originating chat signal is delivered on
        the UI thread. PlainText ensures user-supplied markup is never parsed.
        An empty response denotes a query that has not answered yet.
        """
        if not isinstance(request, str) or not isinstance(response, str):
            return
        if request:
            self.heard.setText(request[:230])
        if response:
            self.reply.setText(response[:250])
        elif request:
            self.reply.setText("ATLAS prépare sa réponse…")
        self._await_reply_line = False

    def ingest_log(self, line: str) -> None:
        """Keep existing speech messages without interpreting them as markup."""
        if not isinstance(line, str):
            return
        for part in line.splitlines():
            stripped = part.strip()
            if stripped.startswith(("📝 Heard:", "⌨️ Typed:")):
                heard = stripped.split(":", 1)[1].strip().strip('"')
                if heard:
                    self.heard.setText(heard[:230])
                self._await_reply_line = False
            elif "🤖 ATLAS" in stripped or "⚠️ ATLAS" in stripped:
                self._await_reply_line = True
            elif self._await_reply_line and stripped:
                if not stripped.startswith(("⏱️", "📝", "🔧", "🔁", "✨", "─")):
                    self.reply.setText(stripped[:250])
                self._await_reply_line = False

    def projection_shape(self) -> QPainterPath:
        """Return the real painted outline for assertions and hit-testing."""
        return _glass_outline(self.width(), self.height())

    def input_region(self) -> QRegion:
        # Coarse polygon construction is cheap, unlike pixmap-alpha scanning.
        return QRegion(self.projection_shape().toFillPolygon().toPolygon())

    def _glass_card_top(self, label: QLabel) -> float:
        """Keep floating-card upper border below its live section heading.

        The narrow and desktop layouts use different Qt spacing, so a
        constant top offset previously crossed the label text.
        """
        caption = self.reply_caption if label is self.reply else self.heard_caption
        content_top = label.geometry().top()
        return float(min(content_top - 2, max(content_top - 15, caption.geometry().bottom() + 4)))

    def _glass_card(self, painter: QPainter, label: QLabel, accent: QColor, w: float):
        """Cut glass strips follow live label placement, not hard-coded text."""
        r = label.geometry()
        top = self._glass_card_top(label)
        bottom = r.bottom() + 7
        if bottom <= top:
            return
        reply = label is self.reply
        # Stagger the floating panes independently of their real text layout.
        # On compact screens retain the original footprint for accessibility.
        offset = 12 if reply and w >= 390 else 0
        left = max(16, r.left() - 10 + offset)
        right = min(w - 14, r.right() + 11 - (14 if reply and w >= 390 else 0))
        if right - left < 16:
            return
        if self._sculpted and w >= 390 and self.height() >= 300:
            # Functional words retain their Qt geometry while the *body*
            # becomes a genuinely asymmetric cut glass wing. The concave
            # bottom notch on replies creates negative space between layers.
            slab = QPainterPath(QPointF(left + 24, top))
            slab.lineTo(right - 62, top)
            slab.lineTo(right - 43, top + 7)
            slab.lineTo(right - 20, top + 5)
            slab.cubicTo(right + 8, top + 8, right + 8, bottom - 16,
                         right - 10, bottom - 7)
            if reply:
                slab.lineTo(right - 63, bottom - 6)
                slab.lineTo(right - 83, bottom - 15)
                slab.lineTo(right - 106, bottom - 15)
                slab.lineTo(right - 124, bottom)
            else:
                slab.lineTo(right - 37, bottom)
            slab.lineTo(left + 38, bottom)
            slab.lineTo(left + 17, bottom - 10)
            slab.lineTo(left + 5, bottom - 10)
            slab.lineTo(left + 5, top + 13)
            slab.closeSubpath()
        else:
            slab = QPainterPath(QPointF(left + 12, top))
            slab.lineTo(right - 31, top)
            slab.lineTo(right - 7, top + 9)
            slab.lineTo(right, top + 22)
            slab.lineTo(right - 7, bottom - 6)
            slab.lineTo(right - 25, bottom)
            slab.lineTo(left + 9, bottom)
            slab.lineTo(left, bottom - 9)
            slab.lineTo(left + 2, top + 10)
            slab.closeSubpath()
        # Hybrid-only optical extrusion: two offset rails suggest a second
        # floating glass skin without another gradient, blur or timer.
        # All strokes stay beneath the live conversation labels.
        if self._cached_effects and self._low_effects and not self._sculpted and w >= 390:
            painter.save()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(3, 14, 33, 105), 3.0))
            painter.drawLine(QPointF(left + 12, bottom + 3),
                             QPointF(right - 26, bottom + 3))
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 118), 1.0))
            painter.drawLine(QPointF(left + 11, bottom + 2),
                             QPointF(right - 25, bottom + 2))
            painter.drawLine(QPointF(right - 6, bottom + 1),
                             QPointF(right + 2, top + 22))
            painter.restore()
        sheen = QLinearGradient(QPointF(left, top), QPointF(right, bottom))
        sheen.setColorAt(0, QColor(12, 98, 164, 183))
        sheen.setColorAt(.48, QColor(4, 39, 81, 207))
        sheen.setColorAt(1, QColor(2, 27, 63, 188))
        painter.fillPath(slab, QBrush(sheen))
        # Two transparent glass skins give the impression of floating depth.
        # These are static strokes, not a blurred drop-shadow or shader.
        painter.setPen(QPen(QColor(12, 194, 255, 34), 5.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(slab)
        painter.setPen(QPen(QColor(91, 226, 255, 105), 1.0))
        painter.drawPath(slab)
        reflection = QLinearGradient(QPointF(left, top), QPointF(left, top + 18))
        reflection.setColorAt(0, QColor(170, 241, 255, 38))
        reflection.setColorAt(1, QColor(170, 241, 255, 0))
        painter.fillPath(
            _facet(((left / w, top / self.height()),
                    ((right - 12) / w, top / self.height()),
                    ((right - 22) / w, (top + 15) / self.height()),
                    ((left + 14) / w, (top + 15) / self.height())),
                   w, self.height()),
            QBrush(reflection),
        )
        edge = QColor(accent)
        edge.setAlpha(220)
        painter.setPen(QPen(edge, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._sculpted and w >= 390 and self.height() >= 300:
            painter.drawLine(QPointF(left + 24, top + .5),
                             QPointF(right - 62, top + .5))
            painter.drawLine(QPointF(left + 5, top + 13),
                             QPointF(left + 5, bottom - 10))
        else:
            painter.drawLine(QPointF(left + 11, top + .5),
                             QPointF(right - 13, top + .5))
            painter.drawLine(QPointF(left + 1, top + 8),
                             QPointF(left + 1, bottom - 5))
        # Offset glass edges suggest layered luminous plexiglas.
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 62), .7))
        if self._sculpted and w >= 390 and self.height() >= 300:
            painter.drawLine(QPointF(left + 38, bottom - 1),
                             QPointF(right - (124 if reply else 37), bottom - 1))
        else:
            painter.drawLine(QPointF(left + 9, bottom - 1),
                             QPointF(right - 8, bottom - 1))
            painter.drawLine(QPointF(right - 6, bottom - 2),
                             QPointF(right - 1, top + 11))

    def _optical_card_image(self, label: QLabel, accent: QColor) -> QImage:
        """Rasterise a floating glass material once, apart from the live text.

        Two small translucent panes cost only Qt QImage memory, not a GPU
        texture or a new timer. Invalidate after layout geometry or DPI change.
        Never cache the QLabel itself: speech content stays interactive/live.
        """
        w, h = self.width(), self.height()
        dpr = max(1.0, float(self.devicePixelRatioF()))
        r = label.geometry()
        top = self._glass_card_top(label)
        is_reply = label is self.reply
        key = (
            "reply" if is_reply else "heard",
            w, h, dpr, r.x(), r.y(), r.width(), r.height(), top,
        )
        cached = self._optical_card_cache.get(key)
        if cached is not None:
            return cached

        # Keep no more than one raster per card, avoiding stale DPI/size
        # buffers during drag between displays.
        if len(self._optical_card_cache) >= 2:
            self._optical_card_cache.clear()
        image = QImage(
            max(1, round(w * dpr)), max(1, round(h * dpr)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        if image.isNull():
            raise RuntimeError("Allocation de la surface optique ATLAS impossible")
        image.setDevicePixelRatio(dpr)
        image.fill(0)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_optical_card_material(painter, label, accent, float(w), top)
        finally:
            painter.end()
        self._optical_card_cache[key] = image
        return image

    def _paint_optical_card_material(
        self, painter: QPainter, label: QLabel, accent: QColor, w: float,
        top: float,
    ) -> None:
        """Three stationary glass planes, bevel and side lens, cached as pixels.

        Deliberately replaces the oversized response notch with a shallow
        optical bevel; no widget, text, hit-region or portrait geometry moves.
        """
        if w < 390 or self.height() < 300:
            return
        r = label.geometry()
        bottom = float(r.bottom() + 7)
        reply = label is self.reply
        offset = 12 if reply else 0
        left = max(16.0, float(r.left() - 10 + offset))
        right = min(w - 14.0, float(r.right() + 11 - (14 if reply else 0)))
        if bottom <= top + 20 or right - left < 120:
            return

        face = QPainterPath(QPointF(left + 23, top + 1))
        face.lineTo(right - 61, top + 1)
        face.lineTo(right - 38, top + 8)
        face.lineTo(right - 20, top + 7)
        face.cubicTo(right + 5, top + 10, right + 7, bottom - 10,
                     right - 14, bottom - 5)
        face.lineTo(right - 36, bottom - 1)
        face.lineTo(left + 31, bottom - 1)
        face.lineTo(left + 7, bottom - 11)
        face.lineTo(left + 7, top + 14)
        face.closeSubpath()

        painter.save()
        # Rear sheet is offset downward. A hard glass edge, never a blur.
        back = QPainterPath(face)
        back.translate(-4, 5)
        painter.fillPath(back, QColor(2, 17, 41, 140))
        painter.setPen(QPen(QColor(accent.red(), accent.green(),
                                  accent.blue(), 87), 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(back)

        # The central dark plane maintains legibility on a bright desktop.
        pane = QLinearGradient(QPointF(left, top), QPointF(right, bottom))
        pane.setColorAt(0, QColor(7, 76, 117, 205))
        pane.setColorAt(.38, QColor(3, 36, 74, 222))
        pane.setColorAt(.75, QColor(2, 24, 60, 225))
        pane.setColorAt(1, QColor(5, 52, 87, 199))
        painter.fillPath(face, QBrush(pane))

        painter.save()
        painter.setClipPath(face)
        # A broad diagonal refraction reads as a transparent upper plane.
        sheen = QPainterPath(QPointF(left + 14, top + 3))
        sheen.lineTo(right - 90, top + 3)
        sheen.lineTo(right - 131, bottom - 2)
        sheen.lineTo(left + 44, bottom - 2)
        sheen.closeSubpath()
        refraction = QLinearGradient(
            QPointF(left, top), QPointF(right - 75, bottom)
        )
        refraction.setColorAt(0, QColor(152, 235, 255, 68))
        refraction.setColorAt(.43, QColor(41, 190, 255, 25))
        refraction.setColorAt(1, QColor(11, 103, 174, 0))
        painter.fillPath(sheen, QBrush(refraction))

        # A contrasting prism cap on the robot-facing side, outside the text.
        prism = QPainterPath(QPointF(right - 57, top + 10))
        prism.lineTo(right - 18, top + 8)
        prism.lineTo(right - 8, bottom - 11)
        prism.lineTo(right - 39, bottom - 3)
        prism.closeSubpath()
        prism_tint = QLinearGradient(
            QPointF(right - 59, top), QPointF(right - 10, bottom)
        )
        prism_tint.setColorAt(0, QColor(20, 173, 241, 19))
        prism_tint.setColorAt(1, QColor(255, 160, 77, 62 if reply else 22))
        painter.fillPath(prism, QBrush(prism_tint))
        painter.restore()

        # Opposed cool/warm facets provide distinct material depth.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(136, 239, 255, 195), 1.4))
        painter.drawLine(QPointF(left + 23, top + 1),
                         QPointF(right - 61, top + 1))
        painter.drawLine(QPointF(left + 7, top + 14),
                         QPointF(left + 7, bottom - 11))
        painter.setPen(QPen(QColor(accent.red(), accent.green(),
                                  accent.blue(), 179), 1.6))
        painter.drawLine(QPointF(right - 38, top + 8),
                         QPointF(right - 20, top + 7))
        painter.drawLine(QPointF(right - 36, bottom - 1),
                         QPointF(left + 31, bottom - 1))
        painter.restore()

    def _paint_neural_details(
        self, painter: QPainter, w: float, h: float, phase: float, activity: bool
    ) -> None:
        """Low-cost layered circuitry inside the glass, never on the portrait."""
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Several faceted rails, with a faint halo and sharp luminous center.
        rails = (
            (((.103, .104), (.165, .067), (.47, .067), (.51, .052)), _CYAN),
            (((.53, .050), (.635, .027), (.79, .027), (.914, .121)), _AMBER),
            (((.079, .322), (.069, .37), (.069, .545)), _CYAN),
            (((.078, .695), (.078, .846), (.193, .944), (.38, .944)), _CYAN),
            (((.59, .950), (.82, .95), (.934, .855)), _AMBER),
        )
        for index, (coords, accent) in enumerate(rails):
            points = [QPointF(x * w, y * h) for x, y in coords]
            glow = QColor(accent)
            glow.setAlpha(36 if activity else 25)
            painter.setPen(QPen(glow, 4.0))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
            thin = QColor(accent)
            thin.setAlpha(179 if index in (1, 4) else 139)
            painter.setPen(QPen(thin, 1.05))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)

        # Two floating plaques and a small vertical diagnostics rail.
        for y, color in ((.295, QColor(65, 211, 255, 58)),
                         (.675, QColor(255, 166, 71, 55))):
            painter.setPen(QPen(color, .8))
            painter.drawLine(QPointF(.17 * w, y * h), QPointF(.83 * w, y * h))
        for offset in range(4):
            y = (.129 + offset * .031) * h
            alpha = 72 + (offset % 2) * 38
            painter.setPen(QPen(QColor(57, 214, 255, alpha), 1.1))
            painter.drawLine(QPointF(.105 * w, y), QPointF(.123 * w, y))

        # Lightweight running bus: no added timer or platform-specific GPU.
        start = .22 * w
        end = .77 * w
        for index in range(24):
            x = start + (end - start) * index / 23
            travel = (phase * (.55 if activity else .12) + index / 24) % 1.0
            lit = travel < .28
            color = QColor(_AMBER if index < 8 else _CYAN)
            color.setAlpha(185 if lit and activity else 76)
            painter.setPen(QPen(color, 1.3 if lit else .8))
            painter.drawLine(QPointF(x, .906 * h),
                             QPointF(x, (.914 if lit else .910) * h))

        # Central optical core; the existing bridge reaches the robot.
        core = QPointF(.52 * w, .963 * h)
        halo = .70 + .30 * math.sin(phase * (4.1 if activity else 1.0))
        for radius, color, alpha, thickness in (
            (16, _CYAN, 48, 3.4),
            (12, _CYAN, 165, 1.25),
            (7.5, _AMBER, 195, 1.5),
        ):
            ring = QColor(color)
            ring.setAlpha(int(alpha * halo))
            painter.setPen(QPen(ring, thickness))
            painter.drawEllipse(core, radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 183, 94, int(190 * halo)))
        painter.drawEllipse(core, 2.7, 2.7)
        painter.restore()

    def _paint_instruments(self, painter: QPainter, w: float, h: float) -> None:
        """Static miniature holographic instruments, kept off the text areas.

        Lines and circles only: no shader, bitmap filter, or new animation timer.
        """
        if w < 390 or h < 280:
            return
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Upper-left orbital scanner. The live heading starts to its right.
        centre = QPointF(42, 37)
        painter.setPen(QPen(QColor(34, 210, 255, 110), 1))
        painter.drawEllipse(centre, 16, 16)
        painter.setPen(QPen(QColor(61, 220, 255, 165), .85))
        painter.drawEllipse(centre, 10.5, 16)
        painter.drawLine(QPointF(26, 37), QPointF(58, 37))
        painter.setPen(QPen(QColor(255, 161, 66, 180), 1.4))
        painter.drawArc(QRectF(21, 16, 42, 42), 40 * 16, 75 * 16)
        # Left diagnostics spine, with unmistakably geometric instrument nodes.
        for index, y in enumerate((.365, .445, .525, .605)):
            x = 37.0
            yy = y * h
            painter.setPen(QPen(QColor(45, 204, 255, 95), 1))
            painter.drawEllipse(QPointF(x, yy), 8, 8)
            painter.setPen(QPen(QColor(255, 168, 70, 125), 1))
            painter.drawLine(QPointF(x - 3, yy), QPointF(x + 3, yy))
            painter.drawLine(QPointF(x, yy - 3), QPointF(x, yy + 3))
            if index < 3:
                painter.setPen(QPen(QColor(55, 179, 238, 78), .8))
                painter.drawLine(QPointF(x, yy + 8), QPointF(x, (.445 + index * .08) * h - 8))
        painter.restore()

    def _paint_message_symbol(
        self, painter: QPainter, label: QLabel, accent: QColor,
        *, microphone: bool
    ) -> None:
        """Compact, real-time QPainter icon in the floated message glass."""
        r = label.geometry()
        if r.width() < 240 or r.height() < 26 or label.contentsMargins().left() == 0:
            return
        c = QPointF(r.left() + 21, r.center().y())
        painter.save()
        painter.setBrush(QColor(2, 35, 61, 195))
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 145), 1.5))
        painter.drawEllipse(c, 15.5, 15.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(209, 245, 255, 220), 1.8))
        if microphone:
            painter.drawRoundedRect(QRectF(c.x() - 3, c.y() - 8, 6, 12), 3, 3)
            painter.drawArc(QRectF(c.x() - 7, c.y() - 6, 14, 15), 188 * 16, 164 * 16)
            painter.drawLine(QPointF(c.x(), c.y() + 8), QPointF(c.x(), c.y() + 11))
            painter.drawLine(QPointF(c.x() - 4, c.y() + 11), QPointF(c.x() + 4, c.y() + 11))
        else:
            # Twin hemispheres with a central neural bridge.
            painter.drawArc(QRectF(c.x() - 10, c.y() - 8, 11, 17), 70 * 16, 230 * 16)
            painter.drawArc(QRectF(c.x(), c.y() - 8, 11, 17), 240 * 16, 230 * 16)
            painter.drawLine(QPointF(c.x(), c.y() - 9), QPointF(c.x(), c.y() + 9))
            painter.drawLine(QPointF(c.x() - 5, c.y() - 1), QPointF(c.x() + 5, c.y() + 3))
        painter.restore()

    def _paint_illuminated_chassis(self, painter: QPainter, w: float, h: float) -> None:
        """Separated, stationary light rails instead of one outer rectangle.

        The negative spaces between rails are intentional: each instrument
        must read as a projected island, not a mechanical screen enclosure.
        """
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rails = (
            (((.055, .255), (.055, .105), (.105, .031), (.265, .031)), _CYAN),
            (((.57, .020), (.81, .020), (.947, .100), (.947, .237)), _AMBER),
            (((.047, .327), (.047, .553), (.019, .627), (.051, .671)), _CYAN),
            (((.051, .745), (.051, .875), (.175, .967), (.327, .967)), _CYAN),
            (((.645, .969), (.824, .969), (.955, .861)), _AMBER),
            (((.94, .715), (.947, .766), (.947, .824)), _CYAN),
        )
        for index, (coords, color) in enumerate(rails):
            path = QPainterPath(QPointF(coords[0][0] * w, coords[0][1] * h))
            for px, py in coords[1:]:
                path.lineTo(px * w, py * h)
            for thickness, alpha in ((6.0, 21), (2.2, 70), (1.1, 187)):
                line = QColor(color)
                line.setAlpha(alpha if index % 2 == 0 else int(alpha * .86))
                painter.setPen(QPen(line, thickness))
                painter.drawPath(path)
        # Measured ticks beneath the individual floating controls.
        for segment in range(14):
            x = (.23 + segment * .035) * w
            painter.setPen(QPen(QColor(54, 215, 255, 112 if segment % 3 else 64), 1.5))
            painter.drawLine(QPointF(x, .963 * h), QPointF(x + .016 * w, .963 * h))
        painter.restore()

    def _paint_controls_island(self, painter: QPainter, w: float, h: float) -> None:
        """A distinct instrument foot below the conversation (no new widgets)."""
        if w < 295 or h < 265:
            return
        buttons = self.voice_button.geometry().united(self.exchanges_button.geometry())
        footer = self.footer.geometry()
        if buttons.isEmpty():
            return
        left = max(19.0, float(buttons.left() - 11))
        right = min(w - 22.0, float(buttons.right() + 12))
        top = float(buttons.top() - 8)
        bottom = min(h - 8.0, float(footer.bottom() + 5))
        if bottom <= top + 20 or right <= left + 60:
            return
        foot = QPainterPath(QPointF(left + 17, top))
        foot.lineTo(right - 25, top)
        foot.lineTo(right, top + 11)
        foot.lineTo(right - 12, bottom - 2)
        foot.lineTo(left + 13, bottom)
        foot.lineTo(left, bottom - 12)
        foot.closeSubpath()
        painter.save()
        fill = QLinearGradient(QPointF(left, top), QPointF(right, bottom))
        fill.setColorAt(0, QColor(1, 40, 73, 169))
        fill.setColorAt(.5, QColor(2, 21, 52, 155))
        fill.setColorAt(1, QColor(4, 39, 63, 126))
        painter.fillPath(foot, QBrush(fill))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(49, 209, 255, 155), 1.0))
        painter.drawLine(QPointF(left + 17, top), QPointF(right - 25, top))
        painter.setPen(QPen(QColor(255, 165, 65, 150), 1.2))
        painter.drawLine(QPointF(right, top + 11), QPointF(right - 12, bottom - 2))
        painter.restore()

    def _paint_telemetry_island(self, painter: QPainter, w: float, h: float) -> None:
        """Independent translucent data crystal, bounded by label geometry."""
        if w < 390 or h < 300:
            return
        reply_bottom = self.reply.geometry().bottom()
        control_top = self.voice_button.geometry().top()
        if control_top - reply_bottom < 21:
            return
        centre = (reply_bottom + control_top) / 2.0
        if self._sculpted:
            # Two physically separate data crystals; the transparent space
            # between them is the design, not another noisy overlay.
            painter.save()
            for left, right, tint, accent in (
                (.17 * w, .59 * w, QColor(2, 40, 75, 155), _CYAN),
                (.68 * w, .87 * w, QColor(48, 35, 32, 143), _AMBER),
            ):
                crystal = QPainterPath(QPointF(left + 13, centre - 10))
                crystal.lineTo(right - 14, centre - 10)
                crystal.lineTo(right, centre)
                crystal.lineTo(right - 12, centre + 10)
                crystal.lineTo(left, centre + 10)
                crystal.lineTo(left - 8, centre)
                crystal.closeSubpath()
                painter.fillPath(crystal, tint)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(accent.red(), accent.green(),
                                          accent.blue(), 135), 1.0))
                painter.drawPath(crystal)
            painter.restore()
            return
        left, right = .175 * w, .87 * w
        top, bottom = centre - 11, centre + 11
        crystal = QPainterPath(QPointF(left + 11, top))
        crystal.lineTo(right - 24, top)
        crystal.lineTo(right, centre)
        crystal.lineTo(right - 22, bottom)
        crystal.lineTo(left, bottom)
        crystal.lineTo(left - 9, centre)
        crystal.closeSubpath()
        painter.save()
        painter.fillPath(crystal, QColor(3, 37, 68, 120))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(40, 200, 255, 105), 1.0))
        painter.drawLine(QPointF(left + 11, top), QPointF(right - 24, top))
        painter.setPen(QPen(QColor(255, 164, 71, 125), 1.0))
        painter.drawLine(QPointF(right, centre), QPointF(right - 22, bottom))
        painter.restore()

    def _paint_header_island(self, painter: QPainter, w: float, h: float) -> None:
        """Separate optical header plane with readable contrast behind live text.

        The title and status are real Qt labels placed above this glass pane.
        No native window, cache invalidation, timer, or face modification.
        """
        if w < 295 or h < 265:
            return
        left = .105 * w
        right = .89 * w
        top = .024 * h
        bottom = .264 * h
        island = QPainterPath(QPointF(left + 14, top))
        island.lineTo(right - 39, top)
        island.lineTo(right, top + 19)
        island.lineTo(right - 7, bottom - 8)
        island.lineTo(right - 33, bottom)
        island.lineTo(left + 6, bottom)
        island.lineTo(left, bottom - 10)
        island.lineTo(left + 3, top + 11)
        island.closeSubpath()
        tint = QLinearGradient(QPointF(left, top), QPointF(right, bottom))
        tint.setColorAt(0, QColor(2, 31, 64, 169))
        tint.setColorAt(.56, QColor(3, 38, 73, 184))
        tint.setColorAt(1, QColor(4, 23, 51, 139))
        painter.save()
        painter.fillPath(island, QBrush(tint))
        painter.setPen(QPen(QColor(48, 210, 255, 112), 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(island)
        painter.setPen(QPen(QColor(255, 162, 72, 145), 1.4))
        painter.drawLine(QPointF(right - 38, top + .5),
                         QPointF(right - 2, top + 19))
        painter.restore()

    def emitter_lens_geometry(self) -> tuple[float, float]:
        """Internal lens center and radius; keeps every optic inside HUD bounds."""
        return (.905 * float(self.width()), 27.0)

    def _paint_orbital_core(self, painter: QPainter, w: float, h: float) -> None:
        """A tiny stationary planetary instrument in the reserved left rail.

        The rings are strokes painted directly by Qt. They allocate no new
        widgets, images, OpenGL contexts or animation timers.
        """
        if w < 390 or h < 280:
            return
        painter.save()
        center = QPointF(39, 39)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(29, 196, 253, 25), 7.0))
        painter.drawEllipse(center, 22, 22)
        painter.setPen(QPen(QColor(62, 212, 255, 165), 1.05))
        painter.drawEllipse(center, 20, 20)
        painter.setPen(QPen(QColor(78, 203, 255, 105), .9))
        painter.drawEllipse(center, 9, 19)
        painter.drawEllipse(center, 19, 8)
        painter.drawLine(QPointF(21, 39), QPointF(57, 39))
        painter.setPen(QPen(QColor(252, 162, 62, 215), 1.75))
        painter.drawArc(QRectF(14, 14, 50, 50), 20 * 16, 84 * 16)
        painter.drawArc(QRectF(14, 14, 50, 50), 195 * 16, 53 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(185, 243, 255, 220))
        painter.drawEllipse(QPointF(39, 39), 2.0, 2.0)
        painter.restore()

    def _paint_telemetry(
        self, painter: QPainter, w: float, h: float, phase: float, activity: bool
    ) -> None:
        """An independent luminous data strip above the real action buttons."""
        if w < 390 or h < 300:
            return
        # Anchored in the unused gap, so real text and buttons stay visible.
        reply_bottom = self.reply.geometry().bottom()
        control_top = self.voice_button.geometry().top()
        if control_top - reply_bottom < 21:
            return
        y = (reply_bottom + control_top) / 2.0
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(55, 196, 248, 65), .8))
        if self._optical:
            # Display sampled percentages instead of the decorative
            # waveform. The existing crystal and layout are unchanged.
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            cpu_text = (
                f"CPU  {self._telemetry_cpu_pct:.0f} %"
                if self._telemetry_cpu_pct is not None else "CPU  --"
            )
            ram_text = (
                f"RAM  {self._telemetry_ram_pct:.0f} %"
                if self._telemetry_ram_pct is not None else "RAM  --"
            )
            painter.setPen(QPen(QColor(139, 235, 255, 233)))
            painter.drawText(
                QRectF(.215*w, y - 10, .31*w, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                cpu_text,
            )
            painter.setPen(QPen(QColor(255, 194, 121, 230)))
            painter.drawText(
                QRectF(.695*w, y - 10, .17*w, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ram_text,
            )
            painter.restore()
            return
        if self._sculpted:
            painter.drawLine(QPointF(.20*w, y), QPointF(.56*w, y))
            painter.drawLine(QPointF(.71*w, y), QPointF(.84*w, y))
        else:
            painter.drawLine(QPointF(.18*w, y), QPointF(.86*w, y))
        # Subdued waveform that reacts only to already-confirmed activity.
        for i in range(13 if self._sculpted else 21):
            x = ((.215 + i * .025) if self._sculpted
                 else (.23 + i * .017)) * w
            strength = (0.55 + 0.45 * math.sin(i * 1.9 + (
                phase * 2.8 if activity else 0.0
            )))
            height = 2.0 + 5.0 * strength
            color = QColor(56, 218, 255, 165 if activity else 85)
            painter.setPen(QPen(color, 1.25))
            painter.drawLine(QPointF(x, y - height), QPointF(x, y + height))
        # Three discrete activity nodes, instead of a large fake graph.
        for i in range(3):
            x = (.73 + .033*i) * w
            color = QColor(255, 171, 67, 205 if i == 0 else 96)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)
        painter.restore()

    def _paint_neural_emitter(
        self, painter: QPainter, w: float, h: float, phase: float, activity: bool
    ) -> None:
        """Distinct blue/amber reactor at the panel's robot-facing notch.

        A small bounded radial gradient creates a luminous lens without
        large-area blur or shadows, even on software raster backends.
        """
        if w < 390:
            return
        center_x, radius = self.emitter_lens_geometry()
        origin = QPointF(center_x, .50 * h)
        pulse = .94 + (.06 * math.sin(phase * 3.0) if activity else 0.0)
        painter.save()
        halo = QRadialGradient(origin, radius)
        halo.setColorAt(0, QColor(194, 249, 255, int(150 * pulse)))
        halo.setColorAt(.13, QColor(53, 210, 255, int(100 * pulse)))
        halo.setColorAt(.55, QColor(14, 137, 255, 44))
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(origin, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(38, 212, 255, 175), 1.3))
        painter.drawEllipse(origin, 17, 17)
        painter.setPen(QPen(QColor(255, 164, 61, 235), 1.6))
        painter.drawArc(QRectF(origin.x()-21, origin.y()-21, 42, 42),
                        32*16, 117*16)
        painter.drawArc(QRectF(origin.x()-21, origin.y()-21, 42, 42),
                        220*16, 57*16)
        painter.setPen(QPen(QColor(138, 230, 255, 187), .9))
        painter.drawLine(QPointF(origin.x()-27, origin.y()),
                         QPointF(origin.x()-9, origin.y()))
        painter.restore()

    def _paint_static_spectral_details(self, painter: QPainter, w: float, h: float) -> None:
        """Static high-detail illumination. Never depends on animation time.

        Both the original paint and the cached composition use these exact
        operations so no separately authored bitmap can alter the robot.
        """
        # Spectral lighting gives the acrylic depth without applying a
        # full-screen blur, OpenGL surface, or a new animation timer.
        for cx, cy, radius, color in (
            (.89, .09, .36, QColor(31, 139, 252, 19)),
            (.13, .91, .30, QColor(20, 193, 252, 15)),
            (.89, .90, .24, QColor(255, 151, 56, 12)),
        ):
            centre = QPointF(cx * w, cy * h)
            light = QRadialGradient(centre, radius * w)
            light.setColorAt(0, color)
            light.setColorAt(1, QColor(0, 0, 0, 0))
            # Paint only the visible light footprint, not the whole pane.
            # This bounds pixel work on the GTR7 for each active repaint.
            reach = radius * w
            x0 = max(0.0, centre.x() - reach)
            y0 = max(0.0, centre.y() - reach)
            x1 = min(w, centre.x() + reach)
            y1 = min(h, centre.y() + reach)
            if x1 > x0 and y1 > y0:
                painter.fillRect(QRectF(x0, y0, x1 - x0, y1 - y0), QBrush(light))
        # Sparse reflection slivers: clear negative space between projections.
        faces = (
            (((.70, .019), (.83, .019), (.95, .095), (.91, .20)),
             QColor(132, 230, 255, 14)),
            (((.046, .64), (.078, .70), (.09, .90), (.05, .85)),
             QColor(46, 194, 249, 12)),
            (((.80, .82), (.955, .85), (.84, .966), (.72, .954)),
             QColor(255, 165, 72, 13)),
        )
        for coords, color in faces:
            painter.fillPath(_facet(coords, w, h), color)

        # Thin tech weave and microcircuits are deliberately subtle to keep
        # the actual conversation readable.
        painter.setPen(QPen(QColor(67, 187, 224, 6), .6))
        for row in range(16, int(h), 28):
            painter.drawLine(QPointF(.09 * w, row), QPointF(.96 * w, row))
        for col in range(22, int(w), 37):
            painter.drawLine(QPointF(col, .07 * h), QPointF(col, .92 * h))

    def _cached_spectral_layer(self) -> QImage:
        """Create one bounded CPU image per Qt size/DPR; no GPU surface.

        This costs work only on first paint or geometry/DPI change and keeps
        the original optical highlights. Image is limited to HUD dimensions.
        """
        width, height = self.width(), self.height()
        dpr = max(1.0, float(self.devicePixelRatioF()))
        key = (width, height, dpr)
        if self._spectral_cache is not None and self._spectral_cache_key == key:
            return self._spectral_cache
        image = QImage(
            max(1, round(width * dpr)),
            max(1, round(height * dpr)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        if image.isNull():
            raise RuntimeError("Allocation du calque holographique impossible")
        image.setDevicePixelRatio(dpr)
        image.fill(0)
        layer_painter = QPainter(image)
        try:
            layer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            layer_painter.setClipPath(self.projection_shape())
            self._paint_static_spectral_details(layer_painter, float(width), float(height))
        finally:
            layer_painter.end()
        self._spectral_cache = image
        self._spectral_cache_key = key
        return image

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        if w < 2 or h < 2:
            painter.end()
            return
        path = self.projection_shape()
        now = time.monotonic()
        phase = now - self._phase_origin
        activity = self._state in _ACTIVE
        glow = .7 + .28 * math.sin(phase * (4.7 if activity else 1.6))
        # The glass is actually translucent and physically cut away, not a
        # dark QPainter rounded rectangle. Transparent pixels remain alpha 0.
        painter.save()
        painter.setClipPath(path)
        tint = QLinearGradient(QPointF(0, 0), QPointF(w, h))
        # Translucent carrier, not a single opaque tablet.  Opaque text
        # islands and light rails sit above the glass on separate planes.
        tint.setColorAt(0, QColor(3, 32, 61, 14))
        tint.setColorAt(.48, QColor(2, 16, 39, 8))
        tint.setColorAt(1, QColor(2, 29, 53, 16))
        painter.fillPath(path, QBrush(tint))

        # Use the same raster-painted glass layer in all modes.
        # Cached mode restores static optical depth to the low-effects
        # projection while retaining its reduced active redraw cadence.
        if self._cached_effects:
            painter.drawImage(QPointF(0, 0), self._cached_spectral_layer())
        elif not self._low_effects:
            self._paint_static_spectral_details(painter, w, h)

        if not self._low_effects:
            self._paint_neural_details(painter, w, h, phase, activity)
        self._paint_header_island(painter, w, h)
        self._paint_controls_island(painter, w, h)
        self._paint_telemetry_island(painter, w, h)
        self._paint_instruments(painter, w, h)
        self._paint_orbital_core(painter, w, h)
        self._paint_telemetry(painter, w, h, phase, activity)
        if self._optical and w >= 390 and h >= 300:
            painter.drawImage(QPointF(0, 0), self._optical_card_image(self.heard, _CYAN))
            painter.drawImage(QPointF(0, 0), self._optical_card_image(self.reply, _AMBER))
        else:
            self._glass_card(painter, self.heard, _CYAN, w)
            self._glass_card(painter, self.reply, _AMBER, w)
        self._paint_message_symbol(painter, self.heard, _CYAN, microphone=True)
        self._paint_message_symbol(painter, self.reply, _AMBER, microphone=False)

        if not self._low_effects:
            # Internal orbit / emitter circuitry near the robot-facing edge.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            cx, cy = .94 * w, .50 * h
            painter.setPen(QPen(QColor(57, 216, 255, 125), 1.1))
            painter.drawArc(QRectF(cx - 13, cy - 13, 26, 26),
                            int((phase * 35) % 360) * 16, 118 * 16)
            painter.setPen(QPen(QColor(255, 160, 75, 125), 1))
            painter.drawArc(QRectF(cx - 19, cy - 19, 38, 38),
                            int((-phase * 22) % 360) * 16, 90 * 16)

            # Several deterministic particles travel along an internal circuit.
            for index in range(9):
                p = (phase * (.07 if activity else .025) + index * .137) % 1
                px = w * (.14 + .72 * p)
                py = h * (.855 - .055 * math.sin(index * 3.2 + p * math.tau))
                c = QColor(_CYAN if index % 3 else _AMBER)
                c.setAlpha(80 if activity else 30)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c)
                painter.drawEllipse(QPointF(px, py), 1.2, 1.2)
        painter.restore()

        # Thin fractured perimeter and luminous contact pads. The exterior
        # corners stay transparent; no square or rectangular frame is drawn.
        edge = QColor(_CYAN)
        edge.setAlpha(int((130 if activity else 95) * glow))
        painter.setPen(QPen(edge, 1.25))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # No continuous perimeter: negative space physically separates
        # the header, live conversation, telemetry and command foot.
        self._paint_illuminated_chassis(painter, w, h)
        painter.setPen(QPen(QColor(255, 165, 77, 180), 1.3))
        painter.drawLine(QPointF(.13 * w, .083 * h), QPointF(.50 * w, .083 * h))
        painter.drawLine(QPointF(.16 * w, .937 * h), QPointF(.59 * w, .937 * h))

        # Animated physical projection from the right-hand emitter; the
        # bridge widget continues it without changing the portrait geometry.
        tip = QPointF(.991 * w, .497 * h)
        painter.setPen(QPen(QColor(54, 223, 255, int(150 * glow)), 1.7))
        painter.drawLine(tip, QPointF(.935 * w, .497 * h))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(103, 227, 255, int(130 * glow)))
        painter.drawEllipse(tip, 2.3, 2.3)
        # Last so the emitter lens sits above the glass and circuitry.
        self._paint_neural_emitter(painter, w, h, phase, activity)

        # First appearance: the projection scans in from the robot-facing
        # right edge, without moving the widget, portrait or actual text.
        if self._revealed_at is not None:
            progress = min(1.0, max(0.0, (now - self._revealed_at) / .66))
            if progress < 1:
                painter.save()
                veil = QColor(4, 17, 30, int((1 - progress) * 80))
                painter.fillPath(path, veil)
                sweep_x = w * (.92 - .82 * progress)
                painter.setPen(QPen(QColor(91, 222, 255, int(160 * (1 - progress))), 1.3))
                painter.drawLine(QPointF(sweep_x, .14 * h), QPointF(sweep_x, .89 * h))
                painter.restore()
        painter.end()


class ProjectionBridge(QWidget):
    """Three luminous circuit strands running from ATLAS to the glass emitter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(47)
        self.setMinimumHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._vertical = False
        self._state = "asleep"
        self._low_effects = os.environ.get("ATLAS_HOLOGRAM_LOW_EFFECTS") == "1"
        self._phase_origin = time.monotonic()
        self._timer = QTimer(self)
        # No continuous redraw in standby. Slow the bridge with low effects.
        self._timer.setInterval(500 if self._low_effects else 250)
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
        if state in _ACTIVE and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._state in _ACTIVE:
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 2 or h < 2:
            painter.end()
            return
        t = time.monotonic() - self._phase_origin
        active = self._state in _ACTIVE
        power = .68 + .30 * math.sin(t * 5.0) if active else .40
        base = QColor(_CYAN)
        base.setAlpha(int(145 * power))
        ember = QColor(_AMBER)
        ember.setAlpha(120)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._vertical:
            x = w / 2
            paths = (
                (QPointF(x, 0), QPointF(x, h)),
                (QPointF(x - 13, 0), QPointF(x - 13, h * .75)),
                (QPointF(x + 13, h * .25), QPointF(x + 13, h)),
            )
            for a, b in paths:
                painter.setPen(QPen(base, 1.2))
                painter.drawLine(a, b)
            painter.setPen(QPen(ember, 1.5))
            painter.drawLine(QPointF(x - 21, h * .57), QPointF(x + 21, h * .57))
            travel = (t * (.8 if active else .3)) % 1
            dot = QPointF(x, h * travel)
        else:
            cy = h * .497
            tracks = (0, -8, 8)
            for dy in tracks:
                path = QPainterPath(QPointF(w, cy + dy))
                path.lineTo(w * .67, cy + dy)
                path.lineTo(w * .44, cy + dy - (7 if dy == 0 else -4))
                path.lineTo(0, cy + dy - (7 if dy == 0 else -4))
                # Double-stroke circuit: static optical halo and narrow core.
                halo = QColor(_CYAN)
                halo.setAlpha(int(43 * power))
                painter.setPen(QPen(halo, 4.0))
                painter.drawPath(path)
                painter.setPen(QPen(base, 1.8 if dy == 0 else 1.05))
                painter.drawPath(path)
            for direction in (-1, 1):
                side = QPainterPath(QPointF(w, cy + direction * 22))
                side.cubicTo(
                    QPointF(w * .72, cy + direction * 14),
                    QPointF(w * .28, cy + direction * 16),
                    QPointF(0, cy + direction * 6),
                )
                painter.setPen(QPen(QColor(255, 165, 69, 45), 3.2))
                painter.drawPath(side)
                painter.setPen(QPen(QColor(255, 169, 81, 135), 1.0))
                painter.drawPath(side)
            painter.setPen(QPen(ember, 1))
            painter.drawLine(QPointF(w * .47, cy - 15), QPointF(w * .47, cy + 16))
            # Luminous source sits next to the unchanged robot silhouette.
            origin = QPointF(w - 4, cy)
            painter.setPen(QPen(QColor(60, 216, 255, 113), 1.3))
            painter.drawEllipse(origin, 9, 9)
            painter.setPen(QPen(QColor(255, 171, 78, 160), 1.0))
            painter.drawEllipse(origin, 5, 5)
            travel = (t * (.8 if active else .28)) % 1
            dot = QPointF(w * (1 - travel), cy)

        painter.setPen(Qt.PenStyle.NoPen)
        halo = QColor(_CYAN)
        halo.setAlpha(int(55 * power))
        painter.setBrush(halo)
        painter.drawEllipse(dot, 4.2, 4.2)
        painter.setBrush(QColor(155, 244, 255, 215))
        painter.drawEllipse(dot, 1.45, 1.45)
        painter.end()
