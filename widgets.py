"""Custom widgets for CapsQual."""
import math
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QFontMetrics


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
    # Zoom controls (sizing)
    ZOOM_BTN_H = 12           # height of each +/- button
    ZOOM_BTN_GAP = 4          # gap between elements in the stack
    ZOOM_PANEL_W = 36         # width of the whole zoom panel (buttons + label)
    ZOOM_MARGIN = 8           # right-edge margin

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Audio data (set via load_audio or set_audio_data)
        self.audio_data = None       # numpy array (float, mono, -1..1)
        self.sample_rate = 44100
        self.duration = 0.0

        # Pre-computed waveform peaks
        self.peaks = None
        self._cached_width = 0

        # Visible viewport (seconds)
        self.view_start = 0.0
        self.view_end = 0.0

        # Default zoom: 15 seconds visible when a segment is first selected
        self._default_zoom = 15.0

        # Segment boundaries (seconds, or None)
        self.start_time = None
        self.end_time = None

        # Playback position (seconds, or None)
        self.playback_position = None

        # Drag state
        self._dragging = None        # 'start' | 'end' | None
        self._drag_offset = 0.0

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
        self.view_start = 0.0
        self.view_end = self.duration
        self._cached_width = 0
        self.peaks = None
        self.update()

    def clear_audio(self):
        """Remove audio data and reset the display."""
        self.audio_data = None
        self.peaks = None
        self.duration = 0.0
        self.view_start = 0.0
        self.view_end = 0.0
        self.start_time = None
        self.end_time = None
        self.playback_position = None
        self.update()

    def set_segment(self, start_seconds, end_seconds):
        """Set segment boundaries and always centre the view on the segment.

        If the view is currently showing the full file, zooms to the
        default zoom level (``_default_zoom`` s).  Otherwise the current
        zoom span is preserved and the viewport re-centres on the segment.
        """
        self.start_time = start_seconds
        self.end_time = end_seconds

        if start_seconds is not None and end_seconds is not None and self.duration > 0:
            is_full = (abs(self.view_start) < 0.001
                       and abs(self.view_end - self.duration) < 0.001)
            vdur = self._default_zoom if is_full else self._view_duration
            center = (start_seconds + end_seconds) / 2.0
            half = vdur / 2.0
            self.view_start = max(0.0, center - half)
            self.view_end = min(self.duration, center + half)
            # If we hit the edge, keep the same zoom width from the opposite side
            if self.view_end - self.view_start < vdur * 0.99:
                if abs(self.view_start) < 0.001:
                    self.view_end = vdur
                else:
                    self.view_start = self.view_end - vdur
            self._cached_width = 0
        else:
            self.view_start = 0.0
            self.view_end = self.duration
            self._cached_width = 0

        self.update()

    def clear_segment(self):
        """Remove segment markers and reset view to full duration."""
        self.start_time = None
        self.end_time = None
        if self.duration > 0:
            self.view_start = 0.0
            self.view_end = self.duration
            self._cached_width = 0
            self.update()

    def set_playback_position(self, seconds):
        """Update the playback position line."""
        self.playback_position = seconds
        self.update()

    def zoom_in(self):
        """Zoom in one step, centered on the middle of the view."""
        self._zoom_at(0.5)

    def zoom_out(self):
        """Zoom out one step, centered on the middle of the view."""
        self._zoom_at(-0.5)

    def _zoom_at(self, direction):
        """Zoom in (direction > 0) or out (direction < 0)."""
        if self.duration <= 0:
            return
        vdur = self._view_duration
        factor = 1.3 if direction > 0 else 1.0 / 1.3
        new_vdur = max(0.05, min(self.duration, vdur * factor))
        center = (self.view_start + self.view_end) / 2.0
        new_start = max(0.0, center - new_vdur / 2.0)
        new_end = min(self.duration, new_start + new_vdur)
        if abs(new_end - new_start - new_vdur) > 0.01:
            new_start = max(0.0, new_end - new_vdur)
        self.view_start = new_start
        self.view_end = new_end
        self._cached_width = 0
        self.update()

    # ── viewport helpers ────────────────────────────────────────

    @property
    def _view_duration(self) -> float:
        if self.duration <= 0:
            return 0.0
        return max(0.001, self.view_end - self.view_start)

    # ── peak computation ───────────────────────────────────────

    def _compute_peaks(self, width: int):
        if self.audio_data is None or width <= 0:
            self.peaks = None
            self._cached_width = width
            return

        import numpy as np
        data = self.audio_data
        sr = float(self.sample_rate)
        n = len(data)

        vstart = max(0.0, self.view_start)
        vend = min(self.duration, self.view_end)
        start_sample = int(vstart * sr)
        end_sample = int(vend * sr)
        if end_sample > n:
            end_sample = n
        span = max(1, end_sample - start_sample)

        self.peaks = np.zeros((width, 2), dtype=np.float32)
        for col in range(width):
            s = start_sample + int(col * span / width)
            e = start_sample + int((col + 1) * span / width)
            if e > s and e <= n:
                chunk = data[s:e]
                self.peaks[col, 0] = float(chunk.min())
                self.peaks[col, 1] = float(chunk.max())
            else:
                self.peaks[col, 0] = 0.0
                self.peaks[col, 1] = 0.0
        self._cached_width = width

    # ── coordinate helpers ─────────────────────────────────────

    def _time_to_x(self, seconds: float) -> int:
        if self.duration <= 0:
            return 0
        margin = self.HANDLE_WIDTH // 2
        w = self.width() - 2 * margin
        if w <= 0:
            return margin
        vdur = self._view_duration
        t = seconds - self.view_start
        t = max(0.0, min(vdur, t))
        return int(margin + t / vdur * w)

    def _x_to_time(self, x: int) -> float:
        if self.duration <= 0:
            return 0
        margin = self.HANDLE_WIDTH // 2
        w = self.width() - 2 * margin
        if w <= 0:
            return self.view_start
        clamped = max(margin, min(self.width() - margin, x))
        f = (clamped - margin) / w
        return self.view_start + f * self._view_duration

    # ── painting ───────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, self.BG_COLOR)

        if self.audio_data is None:
            p.setPen(self.TIME_TEXT_COLOR)
            p.drawText(self.rect(), Qt.AlignCenter, "No audio loaded")
            return

        if self._cached_width != w or self.peaks is None:
            self._compute_peaks(w)
        if self.peaks is None:
            return

        margin = self.HANDLE_WIDTH // 2
        draw_w = w - 2 * margin
        if draw_w <= 0:
            return

        # Selected-region pixel range
        sx_start = self._time_to_x(self.start_time) if self.start_time is not None else None
        sx_end = self._time_to_x(self.end_time) if self.end_time is not None else None

        centre_y = h // 2
        half_h = max(4, (h - 4) // 2)

        # Waveform
        for col in range(draw_w):
            x = margin + col
            pmin, pmax = self.peaks[col]
            pmin = max(-1.0, min(1.0, pmin))
            pmax = max(-1.0, min(1.0, pmax))
            y_top = int(centre_y - pmax * half_h)
            y_bot = int(centre_y - pmin * half_h)

            if sx_start is not None and sx_end is not None and sx_start <= x <= sx_end:
                p.setPen(self.WAVEFORM_SELECTED)
            else:
                p.setPen(self.WAVEFORM_BG)

            if y_bot > y_top:
                p.drawLine(x, y_top, x, y_bot)

        # Playback position
        if self.playback_position is not None and self.duration > 0:
            px = self._time_to_x(self.playback_position)
            p.setPen(QPen(self.PLAYHEAD_COLOR, 1))
            p.drawLine(px, 2, px, h - 2)

        # Segment handles
        hw = self.HANDLE_WIDTH
        for which, tval in [('start', self.start_time), ('end', self.end_time)]:
            if tval is None:
                continue
            hx = self._time_to_x(tval)
            p.setPen(QPen(self.HANDLE_COLOR, 2))
            p.setBrush(self.HANDLE_FILL)
            poly = [
                QPoint(hx, 0),
                QPoint(hx + (hw if which == 'start' else -hw), 0),
                QPoint(hx + (hw if which == 'start' else -hw), h),
                QPoint(hx, h)
            ]
            p.drawPolygon(poly)
            p.setPen(QPen(self.HANDLE_COLOR, 1))
            p.drawLine(hx, 0, hx, h)

        # Time labels
        p.setPen(self.TIME_TEXT_COLOR)
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)

        if self.start_time is not None:
            lbl = self._format_time(self.start_time)
            lx = self._time_to_x(self.start_time)
            tr = p.fontMetrics().boundingRect(lbl)
            lx = max(2, min(lx - tr.width() // 2, w - tr.width() - 2))
            p.drawText(lx, h - 3, lbl)

        if self.end_time is not None:
            lbl = self._format_time(self.end_time)
            lx = self._time_to_x(self.end_time)
            tr = p.fontMetrics().boundingRect(lbl)
            lx = max(2, min(lx - tr.width() // 2, w - tr.width() - 2))
            p.drawText(lx, 12, lbl)

        # ── Zoom controls (vertically centred on right edge) ────
        # Layout:
        #   [+]
        #  15.0s
        #   [−]
        vdur = self._view_duration
        zoom_text = f"{vdur:.1f}s"
        tr = p.fontMetrics().boundingRect(zoom_text)
        panel_w = self.ZOOM_PANEL_W
        btn_h = self.ZOOM_BTN_H
        gap = self.ZOOM_BTN_GAP
        margin = self.ZOOM_MARGIN

        # Total height of the stack
        stack_h = tr.height() + gap + btn_h * 2 + gap
        stack_top = (h - stack_h) // 2
        btn_right = w - margin
        btn_left = btn_right - panel_w

        def _draw_btn(y, label):
            p.setPen(QPen(self.HANDLE_COLOR, 1))
            p.setBrush(QColor(60, 60, 65))
            p.drawRect(btn_left, y, panel_w, btn_h)
            p.setPen(self.TIME_TEXT_COLOR)
            p.drawText(QRect(btn_left, y, panel_w, btn_h), Qt.AlignCenter, label)

        # + button
        _draw_btn(stack_top, '+')
        # Label with opaque background
        label_y = stack_top + btn_h + gap + tr.height()
        label_bg = QRect(btn_left, label_y - tr.height(), panel_w, tr.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(35, 35, 38))
        p.drawRect(label_bg)
        p.setPen(self.TIME_TEXT_COLOR)
        p.drawText(label_bg, Qt.AlignCenter, zoom_text)
        # − button
        _draw_btn(stack_top + btn_h + gap + tr.height() + gap, '−')

    # ── mouse interaction ─────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.duration <= 0:
            return

        x, y = event.x(), event.y()

        # Check zoom button clicks — stack layout: [+], label, [−]
        panel_w = self.ZOOM_PANEL_W
        btn_h = self.ZOOM_BTN_H
        gap = self.ZOOM_BTN_GAP
        margin = self.ZOOM_MARGIN
        text_h = QFontMetrics(self.font()).boundingRect("00.0s").height()
        stack_h = text_h + gap + btn_h * 2 + gap
        stack_top = (self.height() - stack_h) // 2
        btn_right = self.width() - margin
        btn_left = btn_right - panel_w

        plus_rect = QRect(btn_left, stack_top, panel_w, btn_h)
        minus_rect = QRect(btn_left, stack_top + btn_h + gap + text_h + gap, panel_w, btn_h)

        if plus_rect.contains(x, y):
            self.zoom_in()
            event.accept()
            return
        if minus_rect.contains(x, y):
            self.zoom_out()
            event.accept()
            return

        # Check handle proximity
        near_start = near_end = False
        if self.start_time is not None:
            sx = self._time_to_x(self.start_time)
            near_start = abs(x - sx) < self.HANDLE_SNAP_DIST
        if self.end_time is not None:
            ex = self._time_to_x(self.end_time)
            near_end = abs(x - ex) < self.HANDLE_SNAP_DIST

        if near_start and near_end:
            sx = self._time_to_x(self.start_time)
            ex = self._time_to_x(self.end_time)
            if abs(x - sx) >= abs(x - ex):
                near_start = False
            else:
                near_end = False

        if near_start:
            self._dragging = 'start'
            self._drag_offset = self._x_to_time(x) - self.start_time
        elif near_end:
            self._dragging = 'end'
            self._drag_offset = self._x_to_time(x) - self.end_time
        else:
            self.seek_requested.emit(self._x_to_time(x))

        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging is None or self.duration <= 0:
            return

        t = self._x_to_time(event.x()) - self._drag_offset
        t = max(self.view_start, min(self.view_end, t))

        if self._dragging == 'start':
            if self.end_time is not None:
                t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
        elif self._dragging == 'end':
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
        """Scroll wheel: near handles → adjust boundary; elsewhere → zoom."""
        if self.duration <= 0:
            return

        delta = event.angleDelta().y()
        x = event.x()

        # Handle proximity
        near_start = near_end = False
        if self.start_time is not None:
            sx = self._time_to_x(self.start_time)
            near_start = abs(x - sx) < self.HANDLE_SNAP_DIST
        if self.end_time is not None:
            ex = self._time_to_x(self.end_time)
            near_end = abs(x - ex) < self.HANDLE_SNAP_DIST

        if near_start and near_end:
            sx = self._time_to_x(self.start_time)
            ex = self._time_to_x(self.end_time)
            if abs(x - sx) >= abs(x - ex):
                near_start = False
            else:
                near_end = False

        step = 0.5 if not (event.modifiers() & Qt.ShiftModifier) else 0.1
        direction = 1 if delta > 0 else -1

        if near_start and self.start_time is not None:
            t = self.start_time + direction * step
            t = max(self.view_start, min(self.view_end, t))
            if self.end_time is not None:
                t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
            self.update()
        elif near_end and self.end_time is not None:
            t = self.end_time + direction * step
            t = max(self.view_start, min(self.view_end, t))
            if self.start_time is not None:
                t = max(t, self.start_time + 0.001)
            self.end_time = t
            self.segment_end_changed.emit(t)
            self.update()
        else:
            self._zoom_at(direction)
            # Only accept if zoom_btns wasn't just handled
        event.accept()

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _format_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}:{s:05.2f}"

    def sizeHint(self):
        return QSize(400, self.PREFERRED_HEIGHT)
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
            return

        # Outer circle
        painter.setBrush(QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawEllipse(center, radius, radius)

        # Value indicator
        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)
        indicator_length = radius - 2
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
        text_rect = painter.fontMetrics().boundingRect(value_text)
        text_rect.moveCenter(QPoint(int(value_label_x), int(value_label_y)))
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

        # Min/max labels (0.5 and 2.0)
        font.setPointSize(max(6, radius // 5))
        painter.setFont(font)
        label_min = "0.5x"
        label_max = "2.0x"
        min_rect = painter.fontMetrics().boundingRect(label_min)
        max_rect = painter.fontMetrics().boundingRect(label_max)

        min_x = center.x() - radius - min_rect.width() - 5
        min_y = center.y() + radius // 1
        painter.drawText(min_x, min_y, label_min)

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

