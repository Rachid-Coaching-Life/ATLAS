"""Original sculptural hologram for ATLAS's unchanged floating portrait.

All visual effects are real-time Qt raster painting in the *existing* HUD and
connector widgets. No new surface, dependencies, background tasks or assets.
The face artwork, dimensions, geometry and lip animation are not altered.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QRadialGradient, QPainter, QPainterPath, QPen, QRegion,
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

        self._label(self._outer, "DERNIÈRE DEMANDE")
        self.heard = self._message("Prononcez « Atlas » pour commencer.")
        self.heard.setObjectName("atlas_hud_heard")
        self._outer.addWidget(self.heard, 1)

        self._label(self._outer, "RÉPONSE")
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
        # Four visual refreshes per second only during activity.
        # Idle glass remains painted without a perpetual timer.
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.update)

    @staticmethod
    def _label(layout, value):
        label = QLabel(value)
        label.setStyleSheet("color: #65dfff; font-size: 11px; letter-spacing: .4px;")
        layout.addWidget(label)

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
        if self._state in _ACTIVE:
            self._revealed_at = time.monotonic()
            self._timer.start()
        else:
            self._revealed_at = None
            self._timer.stop()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

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

    def _glass_card(self, painter: QPainter, label: QLabel, accent: QColor, w: float):
        """Cut glass strips follow live label placement, not hard-coded text."""
        r = label.geometry()
        top = r.top() - 15
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
        painter.drawLine(QPointF(left + 11, top + .5), QPointF(right - 13, top + .5))
        painter.drawLine(QPointF(left + 1, top + 8), QPointF(left + 1, bottom - 5))
        # Offset glass edges suggest layered luminous plexiglas.
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 62), .7))
        painter.drawLine(QPointF(left + 9, bottom - 1), QPointF(right - 8, bottom - 1))
        painter.drawLine(QPointF(right - 6, bottom - 2), QPointF(right - 1, top + 11))

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
        """Multiple light-weight luminous edges give the pane optical depth."""
        shape = self.projection_shape()
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for width, alpha in ((7.0, 21), (3.0, 54), (1.0, 155)):
            painter.setPen(QPen(QColor(27, 194, 255, alpha), width))
            painter.drawPath(shape)
        # Amber light modules echo the approved blue/orange ATLAS image.
        fragments = (
            ((.62, .018), (.80, .018)),
            ((.81, .018), (.946, .106)),
            ((.10, .905), (.18, .958)),
            ((.66, .974), (.80, .974)),
            ((.81, .974), (.956, .856)),
        )
        for a, b in fragments:
            p1, p2 = QPointF(a[0] * w, a[1] * h), QPointF(b[0] * w, b[1] * h)
            painter.setPen(QPen(QColor(255, 151, 45, 39), 5.0))
            painter.drawLine(p1, p2)
            painter.setPen(QPen(QColor(255, 170, 68, 195), 1.4))
            painter.drawLine(p1, p2)
        # Segmented luminous etchings on the chassis: strong optical signature
        # with only a handful of lines (no continuously animated textures).
        for segment in range(12):
            x = (.25 + segment * .038) * w
            tint = QColor(54, 215, 255, 145 if segment % 3 else 75)
            painter.setPen(QPen(tint, 2.1))
            painter.drawLine(QPointF(x, .958 * h), QPointF(x + .019 * w, .958 * h))
        # Two narrow separated light bars: clearly holographic, never a box.
        painter.setPen(QPen(QColor(42, 206, 255, 125), 1.1))
        painter.drawLine(QPointF(.15 * w, .29 * h), QPointF(.79 * w, .29 * h))
        painter.setPen(QPen(QColor(252, 161, 75, 120), 1.0))
        painter.drawLine(QPointF(.17 * w, .666 * h), QPointF(.77 * w, .666 * h))
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
        painter.drawLine(QPointF(.18*w, y), QPointF(.86*w, y))
        # Subdued waveform that reacts only to already-confirmed activity.
        for i in range(21):
            x = (.23 + i * .017) * w
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
        tint.setColorAt(0, QColor(3, 32, 61, 39))
        tint.setColorAt(.48, QColor(2, 16, 39, 24))
        tint.setColorAt(1, QColor(2, 29, 53, 43))
        painter.fillPath(path, QBrush(tint))

        # Spectral lighting gives the acrylic depth without applying a
        # full-screen blur, OpenGL surface, or a new animation timer.
        for cx, cy, radius, color in (
            (.89, .09, .48, QColor(31, 139, 252, 63)),
            (.13, .91, .43, QColor(20, 193, 252, 40)),
            (.89, .90, .32, QColor(255, 151, 56, 33)),
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
        # Narrow facet reflections, kept away from headings and text. Large
        # opaque triangles previously made the panel look like flat polygons.
        faces = (
            (((.70, .019), (.83, .019), (.95, .095), (.91, .20)),
             QColor(132, 230, 255, 25)),
            (((.046, .64), (.078, .70), (.09, .90), (.05, .85)),
             QColor(46, 194, 249, 23)),
            (((.80, .82), (.955, .85), (.84, .966), (.72, .954)),
             QColor(255, 165, 72, 20)),
        )
        for coords, color in faces:
            painter.fillPath(_facet(coords, w, h), color)

        # Thin tech weave and microcircuits are deliberately subtle to keep
        # the actual conversation readable.
        painter.setPen(QPen(QColor(67, 187, 224, 13), .6))
        for row in range(16, int(h), 28):
            painter.drawLine(QPointF(.09 * w, row), QPointF(.96 * w, row))
        for col in range(22, int(w), 37):
            painter.drawLine(QPointF(col, .07 * h), QPointF(col, .92 * h))

        self._paint_neural_details(painter, w, h, phase, activity)
        self._paint_header_island(painter, w, h)
        self._paint_instruments(painter, w, h)
        self._paint_orbital_core(painter, w, h)
        self._paint_telemetry(painter, w, h, phase, activity)
        self._glass_card(painter, self.heard, _CYAN, w)
        self._glass_card(painter, self.reply, _AMBER, w)
        self._paint_message_symbol(painter, self.heard, _CYAN, microphone=True)
        self._paint_message_symbol(painter, self.reply, _AMBER, microphone=False)

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
        painter.drawPath(path)
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
        self._phase_origin = time.monotonic()
        self._timer = QTimer(self)
        # No continuous redraw of a transparent surface in standby.
        self._timer.setInterval(250)
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
