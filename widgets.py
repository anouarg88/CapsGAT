"""Custom widgets for CapsQual."""
import math
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtGui import QPainter, QPen, QColor


# ── Waveform Viewer ───────────────────────────────────────────────

class WaveformViewer(QWidget):
    """A waveform viewer with draggable segment-boundary markers.

    Displays an audio waveform and lets the user visually adjust
    segment start/end times by dragging handle bars.

    Signals
    -------
    segment_start_changed(start_seconds: float)
        Emitted when the left (start) handle is dragged.
    segment_end_changed(end_seconds: float)
        Emitted when the right (end) handle is dragged.
    seek_requested(seconds: float)
        Emitted when the user clicks inside the waveform (seek).
    """
    segment_start_changed = pyqtSignal(float)
    segment_end_changed = pyqtSignal(float)
    seek_requested = pyqtSignal(float)

    # ── colours ──────────────────────────────────────────────────
    BG_COLOR = QColor(45, 45, 48)
    WAVEFORM_BG = QColor(80, 80, 85)
    WAVEFORM_FG = QColor(140, 140, 150)
    WAVEFORM_SELECTED = QColor(70, 150, 240)
    HANDLE_COLOR = QColor(255, 180, 50)
    HANDLE_FILL = QColor(255, 200, 80)
    PLAYHEAD_COLOR = QColor(255, 80, 80)
    TIME_TEXT_COLOR = QColor(200, 200, 200)
    HANDLE_WIDTH = 8          # pixels
    HANDLE_SNAP_DIST = 10     # pixels — how close to grab a handle
    MIN_HEIGHT = 60
    PREFERRED_HEIGHT = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Audio data (set via load_audio or set_audio_data)
        self.audio_data = None       # numpy array (float, mono, -1..1)
        self.sample_rate = 44100
        self.duration = 0.0

        # Pre-computed waveform peaks — list of (min, max) per pixel column
        self.peaks = None
        self._cached_width = 0

        # Segment boundaries (seconds, or None)
        self.start_time = None
        self.end_time = None

        # Playback position (seconds, or None)
        self.playback_position = None

        # Drag state
        self._dragging = None        # 'start' | 'end' | None
        self._drag_offset = 0.0      # time offset from mouse pos to handle

    # ── public API ──────────────────────────────────────────────

    def load_audio(self, audio_path: str):
        """Load an audio file and compute waveform peaks."""
        try:
            import numpy as np
            import soundfile as sf
            data, sr = sf.read(audio_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            if data.dtype != np.float32 and data.dtype != np.float64:
                data = data.astype(np.float32) / 32768.0
            self.set_audio_data(data, sr)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"WaveformViewer could not load {audio_path}: {e}"
            )
            self.clear_audio()

    def set_audio_data(self, data, sample_rate: int):
        """Set audio data directly from a numpy array (mono, -1..1)."""
        import numpy as np
        self.audio_data = np.asarray(data, dtype=np.float32)
        self.sample_rate = int(sample_rate)
        self.duration = len(self.audio_data) / self.sample_rate
        self._cached_width = 0   # force re-compute on next paint
        self.peaks = None
        self.update()

    def clear_audio(self):
        """Remove audio data and reset the display."""
        self.audio_data = None
        self.peaks = None
        self.duration = 0.0
        self.start_time = None
        self.end_time = None
        self.playback_position = None
        self.update()

    def set_segment(self, start_seconds: float | None,
                    end_seconds: float | None):
        """Set the visible segment boundaries."""
        self.start_time = start_seconds
        self.end_time = end_seconds
        self.update()

    def clear_segment(self):
        """Remove segment markers."""
        self.start_time = None
        self.end_time = None
        self.update()

    def set_playback_position(self, seconds: float | None):
        """Update the playback position line."""
        self.playback_position = seconds
        self.update()

    # ── peak computation ───────────────────────────────────────

    def _compute_peaks(self, width: int):
        """Pre-compute (min, max) peak pairs for each pixel column."""
        if self.audio_data is None or width <= 0:
            self.peaks = None
            self._cached_width = width
            return

        import numpy as np
        data = self.audio_data
        n = len(data)
        self.peaks = np.zeros((width, 2), dtype=np.float32)

        for col in range(width):
            start_idx = int(col * n / width)
            end_idx = int((col + 1) * n / width)
            if end_idx > start_idx:
                chunk = data[start_idx:end_idx]
                self.peaks[col, 0] = chunk.min()
                self.peaks[col, 1] = chunk.max()
            else:
                self.peaks[col, 0] = 0
                self.peaks[col, 1] = 0

        self._cached_width = width

    # ── coordinate helpers ─────────────────────────────────────

    def _time_to_x(self, seconds: float) -> int:
        """Convert a time in seconds to a pixel x-coordinate."""
        if self.duration <= 0:
            return 0
        margin = self.HANDLE_WIDTH // 2
        w = self.width() - 2 * margin
        if w <= 0:
            return margin
        return int(margin + seconds / self.duration * w)

    def _x_to_time(self, x: int) -> float:
        """Convert a pixel x-coordinate to a time in seconds."""
        if self.duration <= 0:
            return 0
        margin = self.HANDLE_WIDTH // 2
        w = self.width() - 2 * margin
        if w <= 0:
            return 0
        clamped = max(margin, min(self.width() - margin, x))
        return (clamped - margin) / w * self.duration

    # ── painting ───────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, self.BG_COLOR)

        if self.audio_data is None:
            painter.setPen(self.TIME_TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignCenter, "No audio loaded")
            return

        if self._cached_width != w:
            self._compute_peaks(w)

        if self.peaks is None:
            return

        margin = self.HANDLE_WIDTH // 2
        draw_w = w - 2 * margin
        if draw_w <= 0:
            return

        # ── Determine selected-region pixel range ────────────
        sel_start_x = None
        sel_end_x = None
        if self.start_time is not None and self.duration > 0:
            sel_start_x = self._time_to_x(self.start_time)
        if self.end_time is not None and self.duration > 0:
            sel_end_x = self._time_to_x(self.end_time)

        centre_y = h // 2
        half_h = max(4, (h - 4) // 2)

        # ── Draw waveform ────────────────────────────────────
        # We draw in two passes: first the background (non-selected)
        # part, then the selected part on top with brighter colours.

        for col in range(draw_w):
            x = margin + col
            pmin, pmax = self.peaks[col]
            # Clamp to -1..1
            pmin = max(-1.0, min(1.0, pmin))
            pmax = max(-1.0, min(1.0, pmax))

            y_top = int(centre_y - pmax * half_h)
            y_bot = int(centre_y - pmin * half_h)

            if sel_start_x is not None and sel_end_x is not None:
                if sel_start_x <= x <= sel_end_x:
                    painter.setPen(self.WAVEFORM_SELECTED)
                else:
                    painter.setPen(self.WAVEFORM_BG)
            else:
                painter.setPen(self.WAVEFORM_BG)

            if y_bot > y_top:
                painter.drawLine(x, y_top, x, y_bot)

        # ── Draw playback position ────────────────────────────
        if self.playback_position is not None and self.duration > 0:
            px = self._time_to_x(self.playback_position)
            painter.setPen(QPen(self.PLAYHEAD_COLOR, 1))
            painter.drawLine(px, 2, px, h - 2)

        # ── Draw segment handles ──────────────────────────────
        hw = self.HANDLE_WIDTH
        for which, time_val in [('start', self.start_time),
                                 ('end', self.end_time)]:
            if time_val is None or self.duration <= 0:
                continue
            hx = self._time_to_x(time_val)
            # Handle triangle
            painter.setPen(QPen(self.HANDLE_COLOR, 2))
            painter.setBrush(self.HANDLE_FILL)
            if which == 'start':
                points = [QPoint(hx, 0), QPoint(hx + hw, 0),
                          QPoint(hx, h + 1), QPoint(hx + hw, h + 1)]
            else:
                points = [QPoint(hx - hw, 0), QPoint(hx, 0),
                          QPoint(hx - hw, h + 1), QPoint(hx, h + 1)]
            # Draw as two triangles forming a trapezoid
            poly = [
                QPoint(hx, 0),
                QPoint(hx + (hw if which == 'start' else -hw), 0),
                QPoint(hx + (hw if which == 'start' else -hw), h),
                QPoint(hx, h)
            ] if which == 'start' else [
                QPoint(hx, 0),
                QPoint(hx - hw, 0),
                QPoint(hx - hw, h),
                QPoint(hx, h)
            ]
            painter.drawPolygon(poly)

            # Vertical line at handle
            painter.setPen(QPen(self.HANDLE_COLOR, 1))
            painter.drawLine(hx, 0, hx, h)

        # ── Time labels ───────────────────────────────────────
        painter.setPen(self.TIME_TEXT_COLOR)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        if self.duration > 0:
            # Current segment times if available
            if self.start_time is not None:
                label = self._format_time(self.start_time)
                lx = self._time_to_x(self.start_time)
                tr = painter.fontMetrics().boundingRect(label)
                lx = max(2, min(lx - tr.width() // 2,
                                self.width() - tr.width() - 2))
                painter.drawText(lx, h - 3, label)

            if self.end_time is not None:
                label = self._format_time(self.end_time)
                lx = self._time_to_x(self.end_time)
                tr = painter.fontMetrics().boundingRect(label)
                lx = max(2, min(lx - tr.width() // 2,
                                self.width() - tr.width() - 2))
                painter.drawText(lx, 12, label)

    # ── mouse interaction ─────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.duration <= 0:
            return

        x = event.x()

        # Check if we're near a handle
        near_start = False
        near_end = False
        if self.start_time is not None:
            sx = self._time_to_x(self.start_time)
            near_start = abs(x - sx) < self.HANDLE_SNAP_DIST
        if self.end_time is not None:
            ex = self._time_to_x(self.end_time)
            near_end = abs(x - ex) < self.HANDLE_SNAP_DIST

        if near_start and near_end:
            # Pick the closer one
            sx = self._time_to_x(self.start_time)
            ex = self._time_to_x(self.end_time)
            if abs(x - sx) < abs(x - ex):
                near_end = False
            else:
                near_start = False

        if near_start:
            self._dragging = 'start'
            self._drag_offset = self._x_to_time(x) - self.start_time
        elif near_end:
            self._dragging = 'end'
            self._drag_offset = self._x_to_time(x) - self.end_time
        else:
            # Click-to-seek
            sec = self._x_to_time(x)
            self.seek_requested.emit(sec)

        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging is None or self.duration <= 0:
            return

        t = self._x_to_time(event.x()) - self._drag_offset
        t = max(0.0, min(self.duration, t))

        if self._dragging == 'start':
            # Don't let start go past end
            if self.end_time is not None:
                t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
        elif self._dragging == 'end':
            # Don't let end go before start
            if self.start_time is not None:
                t = max(t, self.start_time + 0.001)
            self.end_time = t
            self.segment_end_changed.emit(t)

        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging is not None:
            self._dragging = None
            event.accept()

    def wheelEvent(self, event):
        """Scroll wheel adjusts segment boundaries (with Shift for fine)."""
        if self.duration <= 0:
            return
        delta = event.angleDelta().y()
        step = 0.5 if not (event.modifiers() & Qt.ShiftModifier) else 0.1

        # Determine which boundary to adjust based on cursor proximity
        if self.start_time is not None:
            sx = self._time_to_x(self.start_time)
        else:
            sx = -999
        if self.end_time is not None:
            ex = self._time_to_x(self.end_time)
        else:
            ex = 999

        x = event.x()
        near_start = abs(x - sx) < self.HANDLE_SNAP_DIST
        near_end = abs(x - ex) < self.HANDLE_SNAP_DIST

        direction = 1 if delta > 0 else -1

        if near_start and near_end:
            # Pick closer one
            if abs(x - sx) < abs(x - ex):
                near_end = False
            else:
                near_start = False

        if near_start and self.start_time is not None:
            t = self.start_time + direction * step
            t = max(0.0, min(self.duration, t))
            if self.end_time is not None:
                t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
            self.update()
        elif near_end and self.end_time is not None:
            t = self.end_time + direction * step
            t = max(0.0, min(self.duration, t))
            if self.start_time is not None:
                t = max(t, self.start_time + 0.001)
            self.end_time = t
            self.segment_end_changed.emit(t)
            self.update()

        event.accept()

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS.mmm."""
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}:{s:05.2f}"

    def sizeHint(self):
        return QSize(400, self.PREFERRED_HEIGHT)


class SpeedKnob(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 1.0
        self.min_value = 0.5
        self.max_value = 2.0
        self.step = 0.1
        self.is_dragging = False
        self.last_mouse_pos = None
        self.setMinimumSize(30, 30)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
    def sizeHint(self):
        return QSize(60, 60)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = QPoint(self.width() // 2, self.height() // 2)
        radius = min(self.width(), self.height()) // 2 - 5
        if radius < 5:
            return  # too small to draw anything

        # Outer circle
        painter.setBrush(QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawEllipse(center, radius, radius)

        # Value indicator
        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)
        indicator_length = radius - 2  # stay inside circle
        end_x = center.x() + indicator_length * math.cos(angle_rad)
        end_y = center.y() + indicator_length * math.sin(angle_rad)

        painter.setPen(QPen(QColor(0, 120, 215), 2))
        painter.drawLine(center, QPoint(int(end_x), int(end_y)))

        # Center dot
        painter.setBrush(QColor(0, 120, 215))
        painter.setPen(Qt.NoPen)
        dot_radius = max(2, radius // 10)
        painter.drawEllipse(center, dot_radius, dot_radius)

        # Value text
        text_color = self.palette().text().color()
        painter.setPen(text_color)
        font = painter.font()
        font_size = max(7, radius // 4)
        font.setPointSize(font_size)
        painter.setFont(font)
        value_text = f"{self.value:.1f}x"

        value_label_x = center.x()
        value_label_y = center.y() + radius / 2

        # Compute bounding rectangle of the text and centre it on the target point
        text_rect = painter.fontMetrics().boundingRect(value_text)
        text_rect.moveCenter(QPoint(int(value_label_x), int(value_label_y)))
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

      # Min/max labels (0.5 and 2.0)
        font.setPointSize(max(6, radius // 5))
        painter.setFont(font)
        label_min = "0.5x"
        label_max = "2.0x"

        # Get text bounding rectangles
        min_rect = painter.fontMetrics().boundingRect(label_min)
        max_rect = painter.fontMetrics().boundingRect(label_max)

        # Position min label to the left of the circle
        min_x = center.x() - radius - min_rect.width() - 5
        min_y = center.y() + radius // 1   # adjust vertical position as needed
        painter.drawText(min_x, min_y, label_min)

        # Position max label to the right of the circle
        max_x = center.x() + radius + 5
        max_y = center.y() + radius // 1
        painter.drawText(max_x, max_y, label_max)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            event.accept()

    def set_value_direct(self, value):
        """Set value directly"""
        new_value = max(self.min_value, min(self.max_value, value))
        if abs(new_value - self.value) > 0.01:
            self.value = new_value
            self.update()
            self.valueChanged.emit(self.value)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.last_mouse_pos:
            delta_y = self.last_mouse_pos.y() - event.y()
            delta_x = event.x() - self.last_mouse_pos.x()
            delta = delta_y + delta_x

            new_value = self.value + (delta * self.step / 30)
            new_value = max(self.min_value, min(self.max_value, new_value))

            if new_value != self.value:
                self.value = round(new_value / self.step) * self.step
                self.value = max(self.min_value, min(self.max_value, self.value))
                self.update()
                self.valueChanged.emit(self.value)

            self.last_mouse_pos = event.pos()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.last_mouse_pos = None
            event.accept()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_value_direct(self.value + self.step)
        else:
            self.set_value_direct(self.value - self.step)
        event.accept()

