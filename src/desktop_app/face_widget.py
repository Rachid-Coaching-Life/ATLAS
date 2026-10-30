"""ATLAS desktop portrait and legacy animated-face fallback."""

from __future__ import annotations
import math
import random
import time as _time
from typing import Optional
from pathlib import Path
from enum import Enum
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QBoxLayout, QApplication, QMenu
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QPainterPathStroker, QRadialGradient, QRegion, QPixmap
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal

from jarvis.activity import JarvisState, get_jarvis_state
from jarvis.debug import debug_log
from jarvis.output.lip_sync import read_envelope, envelope_level
from desktop_app.themes import COLORS, apply_theme
from desktop_app.hologram_panel import HologramPanel, ProjectionBridge


class Expression(Enum):
    """Available face expressions."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    THINKING = "thinking"
    SURPRISED = "surprised"
    CURIOUS = "curious"
    EXCITED = "excited"
    CONCERNED = "concerned"



class FaceWidget(QWidget):
    """An angular light-beam mask with quiet, time-based expressions.

    Only the connected beams, junctions, eyes and mouth paint over the desktop.
    Motion stays within that silhouette, apart from a close-fitting interaction echo.
    """

    state_observed = pyqtSignal(str)

    DESIGN_WIDTH = 220
    DESIGN_HEIGHT = 280
    FACE_WIDTH = DESIGN_WIDTH * 0.7
    FACE_HEIGHT = FACE_WIDTH * 1.3
    PRIMARY_COLOUR = QColor(COLORS["accent_secondary"])
    INK_COLOUR = QColor(COLORS["bg_primary"])

    def __init__(self, parent=None, *, portrait: bool = True):
        super().__init__(parent)
        self.setMinimumSize(160, 208)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # The installed ATLAS portrait is the production default. The original
        # geometric fallback remains independently testable using portrait=False.
        self._portrait = (
            QPixmap(str(Path(__file__).resolve().parent / "desktop_assets" / "atlas_portrait.png"))
            if portrait else QPixmap()
        )
        self._state_manager = get_jarvis_state()
        self._jarvis_state = JarvisState.ASLEEP
        self._expression = Expression.NEUTRAL
        self._activation_level = 0.0
        self._listening = 0.0
        self._thinking = 0.0
        self._speaking = 0.0
        self._mouth_envelope = None
        self._dictating = 0.0
        self._started_at = _time.monotonic()
        self._last_frame_at = self._started_at
        self._state_entered_at = self._started_at
        self._elapsed = 0.0
        self._state_elapsed = 0.0
        self._listening_started_at: Optional[float] = None
        self._breathing_scale = 1.0
        self._blink_factor = 0.0
        self._blink_started_at: Optional[float] = None
        self._next_blink_at = self._started_at + random.uniform(4.5, 7.5)
        self._glance_started_at: Optional[float] = None
        self._next_glance_at = self._started_at + random.uniform(9.0, 15.0)
        self._glance_target = (0.0, 0.0)
        self._gaze_x = 0.0
        self._gaze_y = 0.0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(33)
        self._animation_timer.timeout.connect(self._animate)

    def showEvent(self, event):
        super().showEvent(event)
        # Observe the latest state immediately, without replaying hidden time.
        now = _time.monotonic()
        self._started_at += now - self._last_frame_at
        self._last_frame_at = now
        self._blink_started_at = None
        self._next_blink_at = now + random.uniform(4.5, 7.5)
        self._glance_started_at = None
        self._next_glance_at = now + random.uniform(9.0, 15.0)
        self._animate()
        self._animation_timer.start()

    def hideEvent(self, event):
        self._animation_timer.stop()
        super().hideEvent(event)

    def set_expression(self, expression: Expression):
        """Set the face expression without changing the assistant's state."""
        if expression != self._expression:
            self._expression = expression
            self.update()

    @staticmethod
    def _approach(value: float, target: float, elapsed: float, duration: float) -> float:
        """Ease a visual property at the same rate on every frame cadence."""
        result = target + (value - target) * math.exp(-elapsed / duration)
        return target if abs(result - target) < 0.0001 else result

    def _animate(self):
        """Observe state once, then advance a bounded amount of visual work."""
        now = _time.monotonic()
        elapsed = max(0.0, now - self._last_frame_at)
        self._last_frame_at = now
        self._elapsed = max(0.0, now - self._started_at)
        previous = self._jarvis_state
        self._jarvis_state = self._state_manager.state
        if self._jarvis_state != previous:
            self._mouth_envelope = None
            self._state_entered_at = now
            if self._jarvis_state == JarvisState.LISTENING:
                self._listening_started_at = now
            self.state_observed.emit(self._jarvis_state.value)
            debug_log(f"👤 Face state: {self._jarvis_state.value}", "face")
        self._state_elapsed = max(0.0, now - self._state_entered_at)
        state = self._jarvis_state
        if state == JarvisState.SPEAKING and self._mouth_envelope is None:
            # TTS publishes after it claims SPEAKING, just before audio start.
            # Retry on later frames until its waveform arrives.
            self._mouth_envelope = read_envelope()
        awake = state != JarvisState.ASLEEP
        self._activation_level = self._approach(self._activation_level, float(awake), elapsed, 0.32)
        for name, target in (
            ("_listening", state == JarvisState.LISTENING),
            ("_thinking", state in (JarvisState.THINKING, JarvisState.DICTATION_PROCESSING)),
            ("_speaking", state == JarvisState.SPEAKING),
            ("_dictating", state in (JarvisState.DICTATING, JarvisState.DICTATION_PROCESSING)),
        ):
            setattr(self, name, self._approach(getattr(self, name), float(target), elapsed, 0.18))
        self._breathing_scale = 1.0 + math.sin(self._elapsed * math.tau / 7.5) * 0.006 * self._activation_level
        self._update_blink(now, awake)
        self._update_glance(now, state == JarvisState.IDLE)
        # Sleeping faces still observe daemon state promptly; hidden ones do no work.
        self._animation_timer.setInterval(
            250 if not awake and self._activation_level == 0.0
            else 50 if state == JarvisState.IDLE else 33
        )
        self.update()

    def _update_blink(self, now: float, awake: bool):
        self._blink_factor = 0.0
        if not awake:
            self._blink_started_at = None
            self._next_blink_at = now + random.uniform(4.5, 7.5)
            return
        if self._blink_started_at is None and now >= self._next_blink_at:
            self._blink_started_at = now
        if self._blink_started_at is not None:
            progress = (now - self._blink_started_at) / 0.28
            if progress < 1.0:
                self._blink_factor = math.sin(progress * math.pi) ** 2
            else:
                self._blink_started_at = None
                self._next_blink_at = now + random.uniform(4.5, 7.5)

    def _update_glance(self, now: float, idle: bool):
        self._gaze_x = self._gaze_y = 0.0
        if not idle:
            self._glance_started_at = None
            self._next_glance_at = now + random.uniform(9.0, 15.0)
            return
        if self._glance_started_at is None and now >= self._next_glance_at:
            self._glance_started_at = now
            self._glance_target = (random.uniform(-2.5, 2.5), random.uniform(-1.0, 1.0))
        if self._glance_started_at is not None:
            progress = (now - self._glance_started_at) / 3.2
            if progress < 1.0:
                envelope = math.sin(progress * math.pi) ** 2
                self._gaze_x = self._glance_target[0] * envelope
                self._gaze_y = self._glance_target[1] * envelope
            else:
                self._glance_started_at = None
                self._next_glance_at = now + random.uniform(9.0, 15.0)

    @staticmethod
    def _portrait_bounds(width: int, height: int, image_width: int, image_height: int) -> QRectF:
        """Center an image without distorting its original aspect ratio."""
        if min(width, height, image_width, image_height) <= 0:
            return QRectF()
        factor = min(width / image_width, height / image_height)
        scaled_width = image_width * factor
        scaled_height = image_height * factor
        return QRectF((width - scaled_width) / 2, (height - scaled_height) / 2,
                      scaled_width, scaled_height)

    @staticmethod
    def _speech_mouth_opening(elapsed: float, speaking: float) -> float:
        """Approximate mouth articulation only while actual playback is active.

        This is an animated mouth, not phoneme-aligned lip synchronisation:
        Piper currently publishes playback state, but no viseme stream.
        """
        if speaking <= 0.02:
            return 0.0
        syllables = abs(math.sin(elapsed * 10.5) * math.cos(elapsed * 3.7 + 0.4))
        return max(0.0, min(1.0, speaking)) * (0.24 + 0.76 * syllables)

    def _paint_portrait_mouth(self, painter: QPainter, bounds: QRectF) -> None:
        """Open the lips over the portrait using Piper's actual audio energy."""
        if self._mouth_envelope is not None:
            # Do not smooth the PCM amplitude by the visual state's
            # 180ms ease-in/out; that delay desynchronises the lips.
            opening = (envelope_level(self._mouth_envelope)
                       if self._jarvis_state == JarvisState.SPEAKING else 0.0)
        else:
            # Legacy TTS backends do not publish a PCM envelope.
            opening = self._speech_mouth_opening(self._elapsed, self._speaking)
        if opening <= 0.02 or bounds.isEmpty():
            return

        # Normalised coordinates refer to the selected ATLAS frontal portrait.
        # QPainter scales the mouth together with the portrait.
        mx = bounds.left() + bounds.width() * 0.503
        my = bounds.top() + bounds.height() * 0.605
        half_width = bounds.width() * 0.105
        jaw_gap = bounds.height() * 0.031 * opening

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        # The dark interior makes an actual opening visible at compact 220px sizes.
        mouth = QPainterPath()
        mouth.moveTo(mx - half_width, my)
        mouth.cubicTo(mx - half_width * 0.52, my - jaw_gap * 0.45,
                      mx + half_width * 0.52, my - jaw_gap * 0.45,
                      mx + half_width, my)
        mouth.cubicTo(mx + half_width * 0.6, my + jaw_gap,
                      mx - half_width * 0.6, my + jaw_gap,
                      mx - half_width, my)
        painter.fillPath(mouth, QColor(25, 9, 16, 240))
        # Soft lip contours move apart with the speaking aperture.
        upper = QPainterPath(QPointF(mx - half_width, my))
        upper.cubicTo(mx - half_width * 0.4, my - jaw_gap * 0.30,
                      mx + half_width * 0.4, my - jaw_gap * 0.30,
                      mx + half_width, my)
        lower = QPainterPath(QPointF(mx - half_width, my))
        lower.cubicTo(mx - half_width * 0.45, my + jaw_gap * 0.95,
                      mx + half_width * 0.45, my + jaw_gap * 0.95,
                      mx + half_width, my)
        outline = QPen(QColor(137, 69, 66, 215))
        outline.setWidthF(max(0.8, bounds.width() * 0.004))
        painter.setPen(outline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(upper)
        painter.drawPath(lower)
        painter.restore()

    def _paint_portrait_blink(self, painter: QPainter, bounds: QRectF) -> None:
        """Temporarily close the eyes while preserving every portrait pixel."""
        closing = max(0.0, min(1.0, self._blink_factor))
        if closing <= 0.025 or bounds.isEmpty():
            return
        w, h = bounds.width(), bounds.height()
        eye_y = bounds.top() + h * 0.372
        radius_x = w * 0.076
        radius_y = h * 0.024
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(85, 56, 42, 243))
        for centre_fraction in (0.318, 0.618):
            cx = bounds.left() + w * centre_fraction
            left, right = cx - radius_x, cx + radius_x
            top = QPainterPath(QPointF(left, eye_y - radius_y))
            top.cubicTo(cx - radius_x * .42, eye_y - radius_y * 1.17,
                        cx + radius_x * .42, eye_y - radius_y * 1.17,
                        right, eye_y - radius_y)
            top.lineTo(right, eye_y - radius_y * (1.0 - closing))
            top.quadTo(cx, eye_y - radius_y * (1.0 - closing * 1.10),
                       left, eye_y - radius_y * (1.0 - closing))
            top.closeSubpath()
            painter.drawPath(top)
            bottom = QPainterPath(QPointF(left, eye_y + radius_y))
            bottom.cubicTo(cx - radius_x * .42, eye_y + radius_y * 1.10,
                           cx + radius_x * .42, eye_y + radius_y * 1.10,
                           right, eye_y + radius_y)
            bottom.lineTo(right, eye_y + radius_y * (1.0 - closing))
            bottom.quadTo(cx, eye_y + radius_y * (1.0 - closing * 1.10),
                          left, eye_y + radius_y * (1.0 - closing))
            bottom.closeSubpath()
            painter.drawPath(bottom)
        painter.restore()

    def _paint_portrait(self, painter: QPainter) -> None:
        """Render the supplied ATLAS portrait with a discreet state cue."""
        bounds = self._portrait_bounds(self.width(), self.height(),
                                      self._portrait.width(), self._portrait.height())
        center_x = bounds.center().x()
        center_y = bounds.center().y()
        scale = 1.0 + 0.006 * math.sin(self._elapsed * math.tau / 7.5) * self._activation_level
        target = QRectF(center_x - bounds.width() * scale / 2,
                        center_y - bounds.height() * scale / 2,
                        bounds.width() * scale, bounds.height() * scale)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, self._portrait, QRectF(self._portrait.rect()))
        self._paint_portrait_blink(painter, target)
        self._paint_portrait_mouth(painter, target)

        # The listening/thinking/speaking indicator is below the facial details.
        active = max(self._listening, self._thinking, self._speaking, self._dictating)
        if active > 0.01:
            colour = QColor("#36c8ff" if self._dictating < 0.5 else "#ffad61")
            colour.setAlphaF(min(0.9, 0.25 + 0.65 * active))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            pulse = 3.0 + active * (1.5 + math.sin(self._elapsed * 5) * 0.8)
            painter.drawEllipse(QPointF(center_x, center_y + bounds.height() * 0.445),
                                pulse, pulse)

    def portrait_input_region(self, width: int, height: int) -> QRegion:
        """Mask transparent portrait pixels without clipping hair or shoulders."""
        bounds = self._portrait_bounds(width, height,
                                      self._portrait.width(), self._portrait.height())
        if bounds.isEmpty():
            return QRegion()
        scaled = self._portrait.scaled(
            max(1, round(bounds.width())), max(1, round(bounds.height())),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        region = QRegion(scaled.mask())
        region.translate(round(bounds.x()), round(bounds.y()))
        return region

    def paintEvent(self, event):
        if not self._portrait.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_portrait(painter)
            painter.end()
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / self.DESIGN_WIDTH, self.height() / self.DESIGN_HEIGHT)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(scale * self._breathing_scale, scale * self._breathing_scale)
        cx, cy, width, height = 0.0, 0.0, self.FACE_WIDTH, self.FACE_HEIGHT
        self._draw_state_contour(painter, cx, cy, width, height)
        contour = self._face_contour(cx, cy, width, height)
        self._stroke(painter, contour, 1.4, 0.46 + 0.4 * self._activation_level)
        self._draw_mask_junctions(painter, contour)
        self._draw_accent_lines(painter, cx, cy, width, height)
        self._draw_beam_flow(painter, contour)
        eye_y = cy - height * 0.15
        for is_left in (True, False):
            eye_x = cx + (-1 if is_left else 1) * width * 0.25
            self._draw_eye(painter, eye_x, eye_y, width * 0.12, self._blink_factor, is_left)
        self._draw_mouth(painter, cx, cy, width, height)
        painter.end()

    @classmethod
    def input_region(cls, width: int, height: int) -> QRegion:
        """Leave empty margins clickable while retaining the face's drag area."""
        scale = min(width / cls.DESIGN_WIDTH, height / cls.DESIGN_HEIGHT)
        contour = cls._face_contour(width / 2, height / 2,
                                    cls.FACE_WIDTH * scale, cls.FACE_HEIGHT * scale)
        padding = QPainterPathStroker()
        padding.setWidth(18 * scale)
        boundary = contour.united(padding.createStroke(contour))
        return QRegion(boundary.toFillPolygon().toPolygon())

    @staticmethod
    def _face_contour(cx: float, cy: float, width: float, height: float) -> QPainterPath:
        """The angular crown, temples and tapered jaw of the light-beam mask."""
        hw, hh = width / 2, height / 2
        vertices = [QPointF(cx + x * hw, cy + y * hh) for x, y in (
            (0, -1), (0.5, -0.85), (0.8, -0.5), (1, -0.1),
            (0.9, 0.3), (0.6, 0.7), (0.3, 0.9), (0, 1),
            (-0.3, 0.9), (-0.6, 0.7), (-0.9, 0.3), (-1, -0.1),
            (-0.8, -0.5), (-0.5, -0.85),
        )]
        path = QPainterPath(vertices[0])
        for vertex in vertices[1:]:
            path.lineTo(vertex)
        path.closeSubpath()
        return path

    def _draw_mask_junctions(self, painter: QPainter, contour: QPainterPath):
        """Small fixed lights join the beams without wandering beyond the mask."""
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(0.46 + 0.4 * self._activation_level)
        for index in range(contour.elementCount() - 1):
            vertex = contour.elementAt(index)
            glow = QRadialGradient(vertex.x, vertex.y, 5.6)
            light = QColor(self.PRIMARY_COLOUR)
            light.setAlpha(140)
            glow.setColorAt(0, light)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(vertex.x, vertex.y), 5.6, 5.6)
            painter.setBrush(self.PRIMARY_COLOUR)
            painter.drawEllipse(QPointF(vertex.x, vertex.y), 2.1, 2.1)
        painter.restore()

    def _draw_accent_lines(self, painter: QPainter, cx: float, cy: float,
                           width: float, height: float):
        """Short cheek beams give the transparent mask its geometric structure."""
        for side in (-1, 1):
            path = QPainterPath(QPointF(cx + side * width * 0.35, cy + height * 0.05))
            path.lineTo(cx + side * width * 0.20, cy + height * 0.05 + width * 0.045)
            self._stroke(painter, path, 1, 0.25 + 0.35 * self._activation_level)

    def _stroke(self, painter: QPainter, path: QPainterPath, width: float,
                opacity: float, colour: Optional[QColor] = None):
        """Draw fine luminous ink, with contrast confined to the same stroke."""
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(opacity)
        ink = QColor(self.INK_COLOUR)
        ink.setAlpha(175)
        pen = QPen(ink, width + 1.7, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
        glow = QColor(colour or self.PRIMARY_COLOUR)
        glow.setAlpha(36)
        pen.setColor(glow)
        pen.setWidthF(width + 3.0)
        painter.setPen(pen)
        painter.drawPath(path)
        pen.setColor(colour or self.PRIMARY_COLOUR)
        pen.setWidthF(width)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.restore()

    def _draw_eye(self, painter: QPainter, ex: float, ey: float,
                  size: float, blink_factor: float, is_left: bool):
        """Diamond eye beams retain the mask identity through expressions and blinks."""
        openness = self._activation_level * (1.0 - blink_factor)
        height = size
        if self._expression == Expression.HAPPY:
            height *= 0.7
        elif self._expression == Expression.SURPRISED:
            height *= 1.16
        elif self._expression in (Expression.SAD, Expression.CONCERNED):
            height *= 0.85
        if self._expression == Expression.CURIOUS and is_left:
            ey -= size * 0.12
        if self._expression == Expression.THINKING:
            ey -= size * 0.08
        height *= openness
        path = QPainterPath(QPointF(ex - size, ey))
        if openness < 0.05:
            path.lineTo(ex + size, ey)
            self._stroke(painter, path, 1.5, 0.52 + self._activation_level * 0.48)
            return
        path.lineTo(ex, ey - height)
        path.lineTo(ex + size, ey)
        path.lineTo(ex, ey + height * 0.5)
        path.closeSubpath()
        opacity = 0.52 + self._activation_level * 0.48
        self._stroke(painter, path, 1.4, opacity)
        if openness < 0.15:
            return
        pupil_size = size * 0.3 * openness
        pupil_x = ex + (self._gaze_x + self._thinking * size * 0.12) * openness
        pupil_y = ey + (self._gaze_y - self._thinking * size * 0.14) * openness
        painter.save()
        painter.setOpacity(opacity)
        painter.setBrush(self.PRIMARY_COLOUR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(pupil_x, pupil_y), pupil_size, pupil_size)
        painter.restore()

    def _draw_beam_flow(self, painter: QPainter, contour: QPainterPath):
        """Coherent energy flows through fixed beams, brighter during processing."""
        if self._activation_level < 0.001:
            return
        # Continuous phase avoids a jump when the assistant changes state.
        phase = self._elapsed / 12 % 1.0
        intensity = self._activation_level * (0.22 + self._thinking * 0.48)
        for offset in (0.0, 0.5):
            for index in range(16):
                start = (phase + offset - index * 0.004) % 1.0
                end = (start + 0.004) % 1.0
                if end < start:
                    continue
                glint = QPainterPath(contour.pointAtPercent(start))
                glint.lineTo(contour.pointAtPercent(end))
                self._stroke(painter, glint, 2.2, intensity * (1 - index / 16),
                             self.PRIMARY_COLOUR.lighter(190))

    def _draw_mouth(self, painter: QPainter, cx: float, cy: float,
                    face_width: float, face_height: float):
        """A straight mask seam opens into a quiet, tapered speaking waveform."""
        half_width = face_width * 0.35
        mouth_y = cy + face_height * 0.25
        amplitude = face_height * 0.035 * self._speaking
        path = QPainterPath(QPointF(cx - half_width, mouth_y))
        for step in range(1, 49):
            t = step / 48
            envelope = math.sin(t * math.pi)
            wave = (math.sin(t * math.tau * 2 - self._elapsed * 9)
                    + 0.25 * math.sin(t * math.tau * 3 + self._elapsed * 6)) / 1.25
            y = mouth_y + amplitude * wave * envelope ** 2
            path.lineTo(cx - half_width + 2 * half_width * t, y)
        self._stroke(painter, path, 1.6, 0.48 + self._activation_level * 0.48)

    def _draw_state_contour(self, painter: QPainter, cx: float, cy: float,
                            width: float, height: float):
        """Keep active cues close to the face rather than sending out large waves."""
        if self._listening > 0.001:
            started = self._listening_started_at or self._last_frame_at
            phase = (self._last_frame_at - started) % 2.0 / 2.0
            scale = 1.025 + phase * 0.035
            contour = self._face_contour(cx, cy, width * scale, height * scale)
            self._stroke(painter, contour, 0.7, (1.0 - phase) * 0.33 * self._listening)
        if self._dictating > 0.001:
            pulse = (1.0 - math.cos(self._state_elapsed * math.tau / 2.4)) / 2
            scale = 1.045 + pulse * 0.008
            contour = self._face_contour(cx, cy, width * scale, height * scale)
            self._stroke(painter, contour, 1.0, (0.4 + pulse * 0.2) * self._dictating,
                         QColor(COLORS['error_light']))


class FaceWindow(QWidget):
    """A standalone window showing the ATLAS portrait or legacy face."""

    def __init__(self, parent=None, *, hologram: bool = False,
                 portrait: bool = True):
        super().__init__(parent)
        self._hologram_enabled = hologram
        self.setWindowTitle("🤖 ATLAS")
        self.setMinimumSize(160, 208)
        self.resize(FaceWidget.DESIGN_WIDTH, FaceWidget.DESIGN_HEIGHT)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setStyleSheet("background: transparent;")
        self.setAccessibleName("Visage d’ATLAS")
        self.setToolTip("Déplacer avec la souris. Clic droit pour les commandes ATLAS.")
        self._tray_menu: Optional[QMenu] = None
        self._drag_offset = None
        self._mask_refresh_queued = False
        self._last_composite_mask_geometry = None

        if self._hologram_enabled:
            # The desktop chooses this single-window projected layout.
            self.hologram = HologramPanel(self)
            self.bridge = ProjectionBridge(self)
            self.face = FaceWidget(self, portrait=portrait)
            self._compact = False
            self._configure_projection()
        else:
            # Retain the isolated silhouette as a tested compatibility mode.
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self.face = FaceWidget(self, portrait=portrait)
            layout.addWidget(self.face)
            if not self.face._portrait.isNull():
                self.setMinimumSize(200, 208)
                image = self.face._portrait
                self.resize(max(200, round(280 * image.width() / image.height())), 280)
        self.face.state_observed.connect(self._update_presence)
        self._update_presence(self.face._state_manager.state.value)

        # Position on the right side of the screen
        self._position_on_right()

    def _configure_projection(self) -> None:
        """Keep the HUD attached to the robot on wide and narrow displays."""
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        width = available.width() if available is not None else 1280
        height = available.height() if available is not None else 800
        self._compact = width < 740
        direction = (
            QBoxLayout.Direction.TopToBottom if self._compact
            else QBoxLayout.Direction.LeftToRight
        )
        layout = QBoxLayout(direction, self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        image = self.face._portrait
        ratio = (image.width() / image.height()
                 if not image.isNull() and image.height() else 0.83)
        if self._compact:
            portrait_h = max(208, min(242, height // 3))
            portrait_w = max(160, round(portrait_h * ratio))
            panel_w = max(210, min(342, width - 24))
            panel_h = max(190, min(245, height - portrait_h - 48))
            self.face.setFixedSize(portrait_w, portrait_h)
            self.hologram.setFixedSize(panel_w, panel_h)
            self.bridge.set_vertical(True)
            self.bridge.setFixedSize(panel_w, 28)
            layout.addWidget(self.face, alignment=Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(self.bridge)
            layout.addWidget(self.hologram)
            self.setMinimumSize(panel_w, portrait_h + 28 + panel_h)
            self.resize(panel_w, portrait_h + 28 + panel_h)
        else:
            portrait_h = max(240, min(330, height - 38))
            portrait_w = max(190, round(portrait_h * ratio))
            # Give the projected glass room on desktop displays while the
            # portrait retains its dimensions and right-screen anchor.
            panel_w = max(265, min(505, width - portrait_w - 47 - 40))
            self.face.setFixedSize(portrait_w, portrait_h)
            self.hologram.setFixedSize(panel_w, portrait_h)
            self.bridge.set_vertical(False)
            self.bridge.setFixedSize(47, portrait_h)
            layout.addWidget(self.hologram)
            layout.addWidget(self.bridge)
            layout.addWidget(self.face)
            total = panel_w + 47 + portrait_w
            self.setMinimumSize(total, portrait_h)
            self.resize(total, portrait_h)

    def ingest_log(self, line: str) -> None:
        """Project real daemon speech and replies via the existing Qt log bus."""
        if self._hologram_enabled:
            self.hologram.ingest_log(line)

    def ingest_chat_preview(self, request: str, response: str) -> None:
        """Project text conversation events without touching the portrait."""
        if self._hologram_enabled:
            self.hologram.set_conversation_preview(request, response)

    def _position_on_right(self):
        """Position the window on the right side of the screen, vertically centered."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        screen_geometry = screen.availableGeometry()
        window_width = self.width()
        window_height = self.height()

        # Position on right side with margin, vertically centered
        margin = 20
        x = screen_geometry.right() - window_width - margin
        y = screen_geometry.top() + (screen_geometry.height() - window_height) // 2

        self.move(x, y)

    def set_expression(self, expression: Expression):
        """Set the face expression."""
        self.face.set_expression(expression)

    def _update_presence(self, state_value: str) -> None:
        """Keep resting states quiet and active interaction clearly visible."""
        state = JarvisState(state_value)
        if self._hologram_enabled:
            opacity = (
                0.84 if state == JarvisState.ASLEEP
                else 0.94 if state == JarvisState.IDLE else 1.0
            )
        else:
            opacity = (
                0.45 if state == JarvisState.ASLEEP
                else 0.72 if state == JarvisState.IDLE else 0.96
            )
        self.setWindowOpacity(opacity)
        if self._hologram_enabled:
            self.hologram.set_activity(state_value)
            self.bridge.set_activity(state_value)

    def _refresh_mask(self) -> None:
        """Limit pointer interception to the active visible silhouette."""
        if not getattr(self, "face", None):
            return
        if not self._hologram_enabled:
            if not self.face._portrait.isNull():
                self.setMask(self.face.portrait_input_region(self.width(), self.height()))
            else:
                self.setMask(FaceWidget.input_region(self.width(), self.height()))
            return
        # Computing an alpha-derived native mask is relatively expensive on
        # Windows. setMask() may itself result in a platform geometry event.
        # Never recompute/reapply it for an unchanged layout.
        geometry = (
            self.width(), self.height(),
            self.face.geometry().getRect(),
            self.hologram.geometry().getRect(),
            self.bridge.geometry().getRect(),
        )
        if geometry == self._last_composite_mask_geometry:
            return
        # The portrait remains visually transparent through Qt's existing
        # WA_TranslucentBackground. A pixel-perfect QBitmap-to-QRegion mask
        # is expensive (and can stall Qt on Windows when unioned with HUD
        # regions). The three tight widget rectangles form a sufficient
        # native hit region for the new combined desktop surface.
        portrait_region = QRegion(self.face.geometry())
        # Match the new glass sculpture's actual polygon, not its old
        # rectangular widget box. This leaves its cut-away corners clickable
        # through to the desktop. The portrait's geometry is untouched.
        projected = self.hologram.input_region().translated(self.hologram.pos())
        connector = QRegion(self.bridge.geometry())
        self._last_composite_mask_geometry = geometry
        self.setMask(projected.united(connector).united(portrait_region))

    def _queue_mask_refresh(self) -> None:
        """Coalesce Qt resize/show events into one post-layout mask update."""
        if not self._hologram_enabled or self._mask_refresh_queued:
            return
        self._mask_refresh_queued = True
        QTimer.singleShot(0, self._flush_mask_refresh)

    def _flush_mask_refresh(self) -> None:
        self._mask_refresh_queued = False
        if self._hologram_enabled and self.isVisible():
            self._refresh_mask()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._queue_mask_refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "face", None) is not None:
            if self._hologram_enabled:
                self._queue_mask_refresh()
            else:
                # Preserve the prior synchronous mask semantics for the
                # tested standalone portrait, including animation snapshots.
                self._refresh_mask()

    def mousePressEvent(self, event) -> None:
        self._drag_offset = None
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is None or not handle.startSystemMove():
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def set_tray_menu(self, menu: QMenu) -> None:
        """Share live actions with the tray, including platform-specific controls."""
        self._tray_menu = menu

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        apply_theme(menu)
        menu.addAction("👤 Masquer ATLAS", self.hide)
        if self._tray_menu is not None:
            menu.addSeparator()
            menu.addActions(self._tray_menu.actions())
        debug_log("face context menu opened", "desktop")
        menu.popup(event.globalPos())
        event.accept()
