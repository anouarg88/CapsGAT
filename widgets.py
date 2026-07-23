"""Custom widgets for CapsQual."""
import math
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QFontMetrics


# ── Waveform Viewer ───────────────────────────────────────────────

class WaveformViewer(QWidget):
    """A waveform viewer with draggable segment-boundary markers.

    Displays an audio waveform and lets the user visually adjust
    segment start/end times by dragging handle bars.  Supports
    dark and light colour themes.

    Signals
    -------
    segment_start_changed(start_seconds: float)
    segment_end_changed(end_seconds: float)
    seek_requested(seconds: float)
    """
    segment_start_changed = pyqtSignal(float)
    segment_end_changed = pyqtSignal(float)
    seek_requested = pyqtSignal(float)

    # ── colour definitions ────────────────────────────────────────

    @staticmethod
    def _dark_theme():
        return {
            'bg': QColor(45, 45, 48),
            'wf_bg': QColor(80, 80, 85),
            'wf_sel': QColor(255, 255, 255),
            'handle': QColor(100, 123, 234),
            'handle_text_bg': QColor(50, 50, 55),
            'playhead': QColor(255, 80, 80),
            'text': QColor(200, 200, 200),
            'zoom_btn': QColor(60, 60, 65),
            'zoom_bg': QColor(35, 35, 38),
            'zoom_text': QColor(200, 200, 200),
        }

    @staticmethod
    def _light_theme():
        return {
            'bg': QColor(255, 255, 255),
            'wf_bg': QColor(200, 200, 205),
            'wf_sel': QColor(0, 0, 0),
            'handle': QColor(100, 123, 234),
            'handle_text_bg': QColor(245, 245, 245),
            'playhead': QColor(255, 80, 80),
            'text': QColor(80, 80, 80),
            'zoom_btn': QColor(220, 220, 220),
            'zoom_bg': QColor(240, 240, 240),
            'zoom_text': QColor(80, 80, 80),
        }

    # ── constants ─────────────────────────────────────────────────
    HANDLE_SNAP_DIST = 10
    HANDLE_TICK = 3          # length of tick marks at handle ends
    HANDLE_PAD = 4           # padding around time label inside handle
    LABEL_H = 14             # height of the timestamp label box
    MIN_HEIGHT = 60
    PREFERRED_HEIGHT = 120
    ZOOM_BTN_H = 12
    ZOOM_BTN_GAP = 4
    ZOOM_PANEL_W = 36
    ZOOM_MARGIN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._theme = 'dark'
        self.C = dict(self._dark_theme())

        # Audio data
        self.audio_data = None
        self.sample_rate = 44100
        self.duration = 0.0
        self.peaks = None
        self._cached_width = 0

        # Viewport
        self.view_start = 0.0
        self.view_end = 0.0
        self._default_zoom = 15.0

        # Segment
        self.start_time = None
        self.end_time = None
        self.playback_position = None

        # Drag state
        self._dragging = None
        self._drag_offset = 0.0

    # ── theme ─────────────────────────────────────────────────────

    def set_theme(self, theme_name):
        """Switch between ``'dark'`` and ``'light'`` colour scheme."""
        self._theme = theme_name
        if theme_name == 'light':
            self.C = dict(self._light_theme())
        else:
            self.C = dict(self._dark_theme())
        self.update()

    # ── public API ────────────────────────────────────────────────

    def load_audio(self, audio_path: str):
        try:
            import numpy as np
            import soundfile as sf
            data, sr = sf.read(audio_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            if data.dtype not in (np.float32, np.float64):
                data = data.astype(np.float32) / 32768.0
            self.set_audio_data(data, sr)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"WaveformViewer could not load {audio_path}: {e}")
            self.clear_audio()

    def set_audio_data(self, data, sample_rate: int):
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
        self.audio_data = None
        self.peaks = None
        self.duration = 0.0
        self.start_time = None
        self.end_time = None
        self.playback_position = None
        self.view_start = 0.0
        self.view_end = 0.0
        self.update()

    def set_segment(self, start_seconds, end_seconds):
        """Store segment boundaries and centre view on the segment.

        On first call (full-file view) the zoom level is set to the
        default (15 s).  Subsequent calls keep the current zoom span
        but re-centre on the new segment.
        """
        self.start_time = start_seconds
        self.end_time = end_seconds

        if start_seconds is not None and end_seconds is not None and self.duration > 0:
            is_full = (abs(self.view_start) < 0.001
                       and abs(self.view_end - self.duration) < 0.001)
            vdur = self._default_zoom if is_full else self._view_duration
            centre = (start_seconds + end_seconds) / 2.0
            half = vdur / 2.0
            self.view_start = max(0.0, centre - half)
            self.view_end = min(self.duration, centre + half)
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
        self.start_time = None
        self.end_time = None
        if self.duration > 0:
            self.view_start = 0.0
            self.view_end = self.duration
            self._cached_width = 0
            self.update()

    def set_playback_position(self, seconds):
        self.playback_position = seconds
        self.update()

    def zoom_in(self):
        self._zoom_at(0.5)

    def zoom_out(self):
        self._zoom_at(-0.5)

    def _zoom_at(self, direction):
        if self.duration <= 0:
            return
        vdur = self._view_duration
        factor = 1.3 if direction > 0 else 1.0 / 1.3
        new_vdur = max(0.05, min(self.duration, vdur * factor))
        centre = (self.view_start + self.view_end) / 2.0
        new_start = max(0.0, centre - new_vdur / 2.0)
        new_end = min(self.duration, new_start + new_vdur)
        if abs(new_end - new_start - new_vdur) > 0.01:
            new_start = max(0.0, new_end - new_vdur)
        self.view_start = new_start
        self.view_end = new_end
        self._cached_width = 0
        self.update()

    # ── viewport helper ───────────────────────────────────────────

    @property
    def _view_duration(self) -> float:
        if self.duration <= 0:
            return 0.0
        return max(0.001, self.view_end - self.view_start)

    # ── peak computation ──────────────────────────────────────────

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
        s0 = int(vstart * sr)
        s1 = int(vend * sr)
        if s1 > n:
            s1 = n
        span = max(1, s1 - s0)
        self.peaks = np.zeros((width, 2), dtype=np.float32)
        for col in range(width):
            a = s0 + int(col * span / width)
            b = s0 + int((col + 1) * span / width)
            if b > a and b <= n:
                chunk = data[a:b]
                self.peaks[col, 0] = float(chunk.min())
                self.peaks[col, 1] = float(chunk.max())
            else:
                self.peaks[col, 0] = 0.0
                self.peaks[col, 1] = 0.0
        self._cached_width = width

    # ── coordinate helpers ────────────────────────────────────────

    def _time_to_x(self, seconds):
        if self.duration <= 0:
            return 0
        m = self.HANDLE_TICK + 1
        w = max(1, self.width() - 2 * m)
        t = max(0.0, min(self._view_duration, seconds - self.view_start))
        return int(m + t / self._view_duration * w)

    def _x_to_time(self, x):
        if self.duration <= 0:
            return 0
        m = self.HANDLE_TICK + 1
        w = max(1, self.width() - 2 * m)
        clamped = max(m, min(self.width() - m, x))
        return self.view_start + ((clamped - m) / w) * self._view_duration

    @staticmethod
    def _handle_half_w(p) -> int:
        """Half-width of a handle based on a wide timestamp sample."""
        tw = p.fontMetrics().boundingRect("0:00.00").width()
        return (tw + 8) // 2 + 1

    # ── painting ──────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()
        C = self.C
        p.fillRect(0, 0, w, h, C['bg'])

        if self.audio_data is None:
            p.setPen(C['text'])
            p.drawText(self.rect(), Qt.AlignCenter, "No audio loaded")
            return

        if self._cached_width != w or self.peaks is None:
            self._compute_peaks(w)
        if self.peaks is None:
            return

        margin = self.HANDLE_TICK + 1
        draw_w = w - 2 * margin
        if draw_w <= 0:
            return

        sx_start = self._time_to_x(self.start_time) if self.start_time is not None else None
        sx_end = self._time_to_x(self.end_time) if self.end_time is not None else None

        centre_y = h // 2
        half_h = max(4, (h - 4) // 2)

        # ── Waveform ──────────────────────────────────────────────
        for col in range(draw_w):
            x = margin + col
            pmin, pmax = self.peaks[col]
            pmin = max(-1.0, min(1.0, pmin))
            pmax = max(-1.0, min(1.0, pmax))
            yt = int(centre_y - pmax * half_h)
            yb = int(centre_y - pmin * half_h)
            p.setPen(C['wf_sel'] if (sx_start is not None and sx_end is not None
                                     and sx_start <= x <= sx_end) else C['wf_bg'])
            if yb > yt:
                p.drawLine(x, yt, x, yb)

        # ── Playback position ─────────────────────────────────────
        if self.playback_position is not None and self.duration > 0:
            px = self._time_to_x(self.playback_position)
            p.setPen(QPen(C['playhead'], 1))
            p.drawLine(px, 2, px, h - 2)

        # ── Segment handles (each is a label box + line + ticks) ──
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)

        hw = self._handle_half_w(p)
        lh = self.LABEL_H
        tick = self.HANDLE_TICK

        for which, tval in [('start', self.start_time), ('end', self.end_time)]:
            if tval is None:
                continue
            hx = self._time_to_x(tval)
            lbl = self._format_time(tval)
            lw = hw * 2

            if which == 'start':
                # Label box flush with top, vertical line down to bottom
                r = QRect(hx - hw, 0, lw, lh)
                p.setPen(QPen(C['handle'], 1))
                p.setBrush(C['handle_text_bg'])
                p.drawRect(r)
                p.setPen(C['text'])
                p.drawText(r, Qt.AlignCenter, lbl)
                p.setPen(QPen(C['handle'], 2))
                p.drawLine(hx, lh, hx, h)
                p.setPen(QPen(C['handle'], 1))
                p.drawLine(hx - tick, h, hx + tick, h)
            else:
                # Label box flush with bottom, vertical line up to top
                r = QRect(hx - hw, h - lh, lw, lh)
                p.setPen(QPen(C['handle'], 1))
                p.setBrush(C['handle_text_bg'])
                p.drawRect(r)
                p.setPen(C['text'])
                p.drawText(r, Qt.AlignCenter, lbl)
                p.setPen(QPen(C['handle'], 2))
                p.drawLine(hx, 0, hx, h - lh)
                p.setPen(QPen(C['handle'], 1))
                p.drawLine(hx - tick, 0, hx + tick, 0)

        p.setFont(font)

        # ── Zoom controls (right edge, vertically centred) ────────
        vdur = self._view_duration
        zoom_text = f"{vdur:.1f}s"
        tr = p.fontMetrics().boundingRect(zoom_text)
        panel_w = self.ZOOM_PANEL_W
        btn_h = self.ZOOM_BTN_H
        gap = self.ZOOM_BTN_GAP

        stack_h = tr.height() + gap + btn_h * 2 + gap
        stack_top = (h - stack_h) // 2
        btn_left = w - self.ZOOM_MARGIN - panel_w

        def _draw_btn(y, label):
            p.setPen(QPen(C['handle'], 1))
            p.setBrush(C['zoom_btn'])
            p.drawRect(btn_left, y, panel_w, btn_h)
            p.setPen(C['zoom_text'])
            p.drawText(QRect(btn_left, y, panel_w, btn_h), Qt.AlignCenter, label)

        _draw_btn(stack_top, '+')
        label_y = stack_top + btn_h + gap + tr.height()
        label_bg = QRect(btn_left, label_y - tr.height(), panel_w, tr.height())
        p.setPen(Qt.NoPen)
        p.setBrush(C['zoom_bg'])
        p.drawRect(label_bg)
        p.setPen(C['zoom_text'])
        p.drawText(label_bg, Qt.AlignCenter, zoom_text)
        _draw_btn(stack_top + btn_h + gap + tr.height() + gap, '−')

    # ── mouse interaction ────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.duration <= 0:
            return

        x, y = event.x(), event.y()
        panel_w = self.ZOOM_PANEL_W
        btn_h = self.ZOOM_BTN_H
        gap = self.ZOOM_BTN_GAP
        text_h = QFontMetrics(self.font()).boundingRect("00.0s").height()
        stack_h = text_h + gap + btn_h * 2 + gap
        stack_top = (self.height() - stack_h) // 2
        btn_left = self.width() - self.ZOOM_MARGIN - panel_w

        if QRect(btn_left, stack_top, panel_w, btn_h).contains(x, y):
            self.zoom_in()
            event.accept()
            return
        if QRect(btn_left, stack_top + btn_h + gap + text_h + gap, panel_w, btn_h).contains(x, y):
            self.zoom_out()
            event.accept()
            return

        # Handle proximity
        near_start = near_end = False
        if self.start_time is not None:
            sx = self._time_to_x(self.start_time)
            near_start = abs(x - sx) < self.HANDLE_SNAP_DIST
        if self.end_time is not None:
            ex = self._time_to_x(self.end_time)
            near_end = abs(x - ex) < self.HANDLE_SNAP_DIST

        if near_start and near_end:
            if abs(x - self._time_to_x(self.start_time)) >= abs(x - self._time_to_x(self.end_time)):
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
        if self.duration <= 0:
            return
        delta = event.angleDelta().y()
        x = event.x()

        near_start = near_end = False
        if self.start_time is not None:
            near_start = abs(x - self._time_to_x(self.start_time)) < self.HANDLE_SNAP_DIST
        if self.end_time is not None:
            near_end = abs(x - self._time_to_x(self.end_time)) < self.HANDLE_SNAP_DIST

        if near_start and near_end:
            if abs(x - self._time_to_x(self.start_time)) >= abs(x - self._time_to_x(self.end_time)):
                near_start = False
            else:
                near_end = False

        step = 0.5 if not (event.modifiers() & Qt.ShiftModifier) else 0.1
        direction = 1 if delta > 0 else -1

        if near_start and self.start_time is not None:
            t = max(self.view_start, min(self.view_end, self.start_time + direction * step))
            if self.end_time is not None:
                t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
            self.update()
        elif near_end and self.end_time is not None:
            t = max(self.view_start, min(self.view_end, self.end_time + direction * step))
            if self.start_time is not None:
                t = max(t, self.start_time + 0.001)
            self.end_time = t
            self.segment_end_changed.emit(t)
            self.update()
        else:
            self._zoom_at(direction)
        event.accept()

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _format_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}:{s:05.2f}"

    def sizeHint(self):
        return QSize(400, self.PREFERRED_HEIGHT)


# ── Speed Knob ────────────────────────────────────────────────────

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

        painter.setBrush(QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawEllipse(center, radius, radius)

        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)
        ilen = radius - 2
        end_x = center.x() + ilen * math.cos(angle_rad)
        end_y = center.y() + ilen * math.sin(angle_rad)

        painter.setPen(QPen(QColor(0, 120, 215), 2))
        painter.drawLine(center, QPoint(int(end_x), int(end_y)))

        painter.setBrush(QColor(0, 120, 215))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, max(2, radius // 10), max(2, radius // 10))

        text_color = self.palette().text().color()
        painter.setPen(text_color)
        font = painter.font()
        font.setPointSize(max(7, radius // 4))
        painter.setFont(font)
        value_text = f"{self.value:.1f}x"

        vx = center.x()
        vy = center.y() + radius / 2
        tr = painter.fontMetrics().boundingRect(value_text)
        tr.moveCenter(QPoint(int(vx), int(vy)))
        painter.drawText(tr, Qt.AlignCenter, value_text)

        font.setPointSize(max(6, radius // 5))
        painter.setFont(font)
        for label, side in [("0.5x", -1), ("2.0x", 1)]:
            r = painter.fontMetrics().boundingRect(label)
            x = center.x() + side * (radius + r.width() + 5)
            y = center.y() + radius // 1
            painter.drawText(int(x), y, label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            event.accept()

    def set_value_direct(self, value):
        new_value = max(self.min_value, min(self.max_value, value))
        if abs(new_value - self.value) > 0.01:
            self.value = new_value
            self.update()
            self.valueChanged.emit(self.value)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.last_mouse_pos:
            dy = self.last_mouse_pos.y() - event.y()
            dx = event.x() - self.last_mouse_pos.x()
            delta = dy + dx
            new_value = max(self.min_value, min(self.max_value, self.value + (delta * self.step / 30)))
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
