"""Custom widgets for CapsQual."""
import math
from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QSplitterHandle, QSplitter, QToolButton,
    QPushButton, QHBoxLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QTimer, QObject, QThread
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
    loading_complete = pyqtSignal()  # emitted when audio + peaks are fully ready
    drag_started = pyqtSignal()      # emitted when a segment handle drag begins

    # ── colour definitions ────────────────────────────────────────

    @staticmethod
    def _dark_theme():
        return {
            'bg': QColor(45, 45, 48),
            'wf_bg': QColor(80, 80, 85),
            'wf_sel': QColor(255, 255, 255),
            'handle': QColor(100,123,234),
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
            'bg': QColor(240, 240, 240),
            'wf_bg': QColor(180, 180, 185),
            'wf_sel': QColor(0, 0, 0),
            'handle': QColor(17, 82, 212),
            'handle_text_bg': QColor(245, 245, 245),
            'playhead': QColor(255, 80, 80),
            'text': QColor(80, 80, 80),
            'zoom_btn': QColor(220, 220, 220),
            'zoom_bg': QColor(230, 230, 230),
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
    SPINNER_TICK_MS = 40
    SPINNER_ANGLE_STEP = 12
    SPINNER_BLOCK_COUNT = 7
    SPINNER_BLOCK_W = 10
    SPINNER_BLOCK_GAP = 5
    KEYBOARD_NUDGE_STEP = 0.1  # seconds moved per Ctrl+arrow nudge

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.ClickFocus)  # clicking the waveform enables keyboard control
        self.setToolTip(
            "Waveform keyboard shortcuts:\n"
            "Ctrl+Left/Right            nudge the start marker\n"
            "Ctrl+Shift+Left/Right      nudge the end marker\n"
            "Ctrl+Shift+Alt+Left/Right  set marker to the playhead"
        )
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

        # Loading spinner
        self._loading = False
        self._spinner_angle = 0.0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._on_spinner_tick)
        self._loader_thread = None
        self._loader_worker = None

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
        """Load audio data in a background thread so the UI stays responsive."""
        self._start_loading()
        # Use a background thread so the spinner animates during file I/O
        self._loader_thread = QThread(self)
        self._loader_worker = _AudioLoaderWorker(audio_path)
        self._loader_worker.moveToThread(self._loader_thread)
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.finished.connect(self._on_audio_loaded)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_worker.finished.connect(self._loader_worker.deleteLater)
        self._loader_thread.finished.connect(self._loader_thread.deleteLater)
        self._loader_thread.finished.connect(self._cleanup_loader_refs)
        self._loader_thread.start()

    def _start_loading(self):
        """Show the loading spinner and clear stale waveform data."""
        self.audio_data = None
        self.peaks = None
        self._loading = True
        self._spinner_angle = 0.0
        self._spinner_timer.start(self.SPINNER_TICK_MS)
        self.update()

    def _stop_loading(self):
        """Hide the loading spinner."""
        self._loading = False
        self._spinner_timer.stop()
        self.update()

    def _on_spinner_tick(self):
        """Advance the spinner animation angle."""
        self._spinner_angle = (self._spinner_angle + self.SPINNER_ANGLE_STEP) % 360.0
        self.update()

    def _on_audio_loaded(self, result):
        """Receive audio data from the background loader thread."""
        if result is None:
            import logging
            logging.getLogger(__name__).warning("WaveformViewer: audio load failed")
            self._stop_loading()
            self.loading_complete.emit()
        else:
            data, sr = result
            self.audio_data = data.astype('float32')
            self.sample_rate = int(sr)
            self.duration = len(self.audio_data) / self.sample_rate
            self.view_start = 0.0
            self.view_end = self.duration
            self._cached_width = 0
            self.peaks = None
            # Compute peaks in background so UI stays responsive
            self._peaks_thread = QThread(self)
            self._peaks_worker = _PeaksWorker(
                self.audio_data, self.sample_rate, self.duration,
                self.width(), self.view_start, self.view_end
            )
            self._peaks_worker.moveToThread(self._peaks_thread)
            self._peaks_thread.started.connect(self._peaks_worker.run)
            self._peaks_worker.finished.connect(self._on_peaks_computed)
            self._peaks_worker.finished.connect(self._peaks_thread.quit)
            self._peaks_worker.finished.connect(self._peaks_worker.deleteLater)
            self._peaks_thread.finished.connect(self._peaks_thread.deleteLater)
            self._peaks_thread.start()

    def _on_peaks_computed(self, peaks_result):
        """Receive pre-computed peaks from background thread."""
        self.peaks = peaks_result
        self._cached_width = self.width()
        self._stop_loading()
        self.loading_complete.emit()
        self.update()

    def _cleanup_loader_refs(self):
        """Clear loader thread references after cleanup."""
        self._loader_thread = None
        self._loader_worker = None

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

        if self._loading:
            self._draw_spinner(p, w, h, C)
            return

        if self.audio_data is None or self.peaks is None:
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
                # Label box 1 px from top, vertical line 1 px from bottom
                r = QRect(hx - hw, 1, lw, lh)
                p.setPen(QPen(C['handle'], 1))
                p.setBrush(C['handle_text_bg'])
                p.drawRect(r)
                p.setPen(C['text'])
                p.drawText(r, Qt.AlignCenter, lbl)
                p.setPen(QPen(C['handle'], 2))
                p.drawLine(hx, 1 + lh, hx, h - 1)
                p.setPen(QPen(C['handle'], 1))
                p.drawLine(hx - tick, h - 1, hx + tick, h - 1)
            else:
                # Label box 1 px from bottom, vertical line 1 px from top
                r = QRect(hx - hw, h - lh - 1, lw, lh)
                p.setPen(QPen(C['handle'], 1))
                p.setBrush(C['handle_text_bg'])
                p.drawRect(r)
                p.setPen(C['text'])
                p.drawText(r, Qt.AlignCenter, lbl)
                p.setPen(QPen(C['handle'], 2))
                p.drawLine(hx, 1, hx, h - lh - 1)
                p.setPen(QPen(C['handle'], 1))
                p.drawLine(hx - tick, 1, hx + tick, 1)

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
            self.drag_started.emit()
        elif near_end:
            self._dragging = 'end'
            self._drag_offset = self._x_to_time(x) - self.end_time
            self.drag_started.emit()
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

    def keyPressEvent(self, event):
        """Keyboard control for the segment markers.

        Used when the widget itself has focus (the editor additionally routes
        these keys globally via an application event filter, so they work even
        when another widget has focus).

        - Ctrl+Left/Right       nudge the start marker
        - Ctrl+Shift+Left/Right nudge the end marker
        - Ctrl+Shift+Alt+Left/Right set a marker to the playhead position

        Plain arrow keys are intentionally left untouched so the editor's
        window-level block-navigation shortcuts still work.
        """
        if self.duration > 0 and self.start_time is not None and self.end_time is not None:
            mods = event.modifiers()
            ctrl = bool(mods & Qt.ControlModifier)
            shift = bool(mods & Qt.ShiftModifier)
            alt = bool(mods & Qt.AltModifier)
            key = event.key()

            if ctrl and not alt and key in (Qt.Key_Left, Qt.Key_Right):
                direction = 1 if key == Qt.Key_Right else -1
                which = 'end' if shift else 'start'
                self.keyboard_nudge(which, direction, event.isAutoRepeat())
                event.accept()
                return

            if ctrl and shift and alt and key in (Qt.Key_Left, Qt.Key_Right):
                which = 'start' if key == Qt.Key_Left else 'end'
                self.snap_marker_to_playhead(which, event.isAutoRepeat())
                event.accept()
                return

        super().keyPressEvent(event)

    def keyboard_nudge(self, which, direction, is_auto_repeat=False):
        """Nudge one marker by one step via keyboard.

        ``which`` is ``'start'`` or ``'end'``; ``direction`` is -1 or +1.
        One undo snapshot is pushed per press burst (auto-repeat is deduped).
        """
        if not is_auto_repeat:
            self.drag_started.emit()  # one undo snapshot per press burst
        step = self.KEYBOARD_NUDGE_STEP * direction
        if which == 'start':
            t = self.start_time + step
            t = max(self.view_start, min(self.view_end, t))
            t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
        else:
            t = self.end_time + step
            t = max(self.view_start, min(self.view_end, t))
            t = max(t, self.start_time + 0.001)
            self.end_time = t
            self.segment_end_changed.emit(t)
        self.update()

    def snap_marker_to_playhead(self, which, is_auto_repeat=False):
        """Move a marker to the current playhead position."""
        if is_auto_repeat or self.playback_position is None:
            return
        t = self.playback_position
        t = max(self.view_start, min(self.view_end, t))
        self.drag_started.emit()  # one undo snapshot per action
        if which == 'start':
            t = min(t, self.end_time - 0.001)
            self.start_time = t
            self.segment_start_changed.emit(t)
        else:
            t = max(t, self.start_time + 0.001)
            self.end_time = t
            self.segment_end_changed.emit(t)
        self.update()

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

    def _draw_spinner(self, p, w, h, C):
        """Draw an animated wave-of-blocks loading indicator."""
        import math
        n = self.SPINNER_BLOCK_COUNT
        bw = self.SPINNER_BLOCK_W
        gap = self.SPINNER_BLOCK_GAP
        bar_w = n * bw + (n - 1) * gap
        bx = (w - bar_w) // 2
        by = h // 2 - bw // 2

        phase = math.radians(self._spinner_angle)
        handle_color = C['handle']

        for i in range(n):
            # Opacity follows a travelling sine wave
            alpha = int(55 + 200 * (math.sin(phase - i * 0.9) + 1) / 2)
            color = QColor(handle_color.red(), handle_color.green(),
                           handle_color.blue(), alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(bx + i * (bw + gap), by, bw, bw, 2, 2)

        # "Loading..." text below
        p.setPen(C['text'])
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        text_rect = QRect(0, by + bw + 10, w, 16)
        p.drawText(text_rect, Qt.AlignCenter, "Generating waveform...")

    def sizeHint(self):
        return QSize(400, self.PREFERRED_HEIGHT)


# ── Audio Loader Worker ────────────────────────────────────────────

class _AudioLoaderWorker(QObject):
    """Loads audio data in a background thread and emits the result."""

    finished = pyqtSignal(object)  # emits (data, sample_rate) tuple or None on failure

    def __init__(self, audio_path: str):
        super().__init__()
        self._audio_path = audio_path

    def run(self):
        try:
            import numpy as np
            import soundfile as sf
            data, sr = sf.read(self._audio_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            if data.dtype not in (np.float32, np.float64):
                data = data.astype(np.float32) / 32768.0
            self.finished.emit((data, sr))
        except Exception:
            self.finished.emit(None)


class _PeaksWorker(QObject):
    """Computes waveform peaks in a background thread."""

    finished = pyqtSignal(object)  # emits numpy array of shape (width, 2)

    def __init__(self, audio_data, sample_rate, duration, width, view_start, view_end):
        super().__init__()
        self._audio_data = audio_data
        self._sample_rate = sample_rate
        self._duration = duration
        self._width = width
        self._view_start = view_start
        self._view_end = view_end

    def run(self):
        import numpy as np
        data = self._audio_data
        sr = float(self._sample_rate)
        n = len(data)
        width = self._width
        vstart = max(0.0, self._view_start)
        vend = min(self._duration, self._view_end)
        s0 = int(vstart * sr)
        s1 = int(vend * sr)
        if s1 > n:
            s1 = n
        span = max(1, s1 - s0)
        peaks = np.zeros((width, 2), dtype=np.float32)
        for col in range(width):
            a = s0 + int(col * span / width)
            b = s0 + int((col + 1) * span / width)
            if b > a and b <= n:
                chunk = data[a:b]
                peaks[col, 0] = float(chunk.min())
                peaks[col, 1] = float(chunk.max())
            else:
                peaks[col, 0] = 0.0
                peaks[col, 1] = 0.0
        self.finished.emit(peaks)


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

        pal = self.palette()
        painter.setBrush(pal.button())
        painter.setPen(QPen(pal.mid(), 2))
        painter.drawEllipse(center, radius, radius)

        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)
        ilen = radius - 2
        end_x = center.x() + ilen * math.cos(angle_rad)
        end_y = center.y() + ilen * math.sin(angle_rad)

        painter.setPen(QPen(pal.highlight(), 2))
        painter.drawLine(center, QPoint(int(end_x), int(end_y)))

        painter.setBrush(pal.highlight())
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




# ── Collapsible Splitter ─────────────────────────────────────────

class CollapsibleSplitterHandle(QSplitterHandle):
    def __init__(self, orientation, parent, right_widget):
        super().__init__(orientation, parent)
        self.right_widget = right_widget
        self.collapsed = False
        self.saved_size = None
        
        # Create toggle button
        self.toggle_btn = QToolButton(self)
        self.toggle_btn.setCursor(Qt.ArrowCursor)
        self.toggle_btn.setFixedSize(16, 16)
        self.update_button_icon()
        self.toggle_btn.clicked.connect(self.toggle_collapse)
        
        # Update button position on resize
        self.update_button_position()
        
        # Monitor splitter movement to sync state
        splitter = self.splitter()
        splitter.splitterMoved.connect(self.on_splitter_moved)
    
    def update_button_icon(self):
        if self.collapsed:
            self.toggle_btn.setText("\u25c0")   # arrow left (expand)
        else:
            self.toggle_btn.setText("\u25b6")   # arrow right (collapse)
    
    def update_button_position(self):
        x = (self.width() - self.toggle_btn.width()) // 2
        y = (self.height() - self.toggle_btn.height()) // 2
        self.toggle_btn.move(x, y)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_button_position()
    
    def on_splitter_moved(self, pos, index):
        # After a manual resize, update collapsed state based on current width
        QTimer.singleShot(10, self.update_state_from_size)
    
    def update_state_from_size(self):
        splitter = self.splitter()
        idx = splitter.indexOf(self.right_widget)
        if idx == -1:
            return
        current_width = splitter.sizes()[idx]
        min_width = self.right_widget.minimumWidth()
        is_collapsed = (current_width <= min_width + 5)  # tolerance
        if self.collapsed != is_collapsed:
            self.collapsed = is_collapsed
            self.update_button_icon()
            if is_collapsed:
                pass
    
    def toggle_collapse(self):
        splitter = self.splitter()
        idx = splitter.indexOf(self.right_widget)
        if idx == -1:
            return
        
        if self.collapsed:
            # Expand: restore saved size if available, else use a default
            if self.saved_size is not None:
                new_sizes = splitter.sizes()
                new_sizes[idx] = self.saved_size
                splitter.setSizes(new_sizes)
            self.collapsed = False
        else:
            # Collapse: save current size, then set to minimum
            sizes = splitter.sizes()
            self.saved_size = sizes[idx]
            new_sizes = sizes[:]
            new_sizes[idx] = self.right_widget.minimumWidth()
            splitter.setSizes(new_sizes)
            self.collapsed = True
        self.update_button_icon()


class CollapsibleSplitter(QSplitter):
    def __init__(self, orientation, right_widget):
        super().__init__(orientation)
        self.right_widget = right_widget
    
    def createHandle(self):
        return CollapsibleSplitterHandle(self.orientation(), self, self.right_widget)


# ── Theme Toggle ──────────────────────────────────────────────────

class ThemeToggle(QWidget):
    """Pill-style light/dark toggle switch."""

    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._light_btn = QPushButton("Light mode")
        self._dark_btn = QPushButton("Dark mode")
        self._light_btn.setFixedHeight(28)
        self._dark_btn.setFixedHeight(28)
        self._light_btn.clicked.connect(lambda: self.set_dark(False))
        self._dark_btn.clicked.connect(lambda: self.set_dark(True))
        layout.addWidget(self._light_btn)
        layout.addWidget(self._dark_btn)
        self._apply_style()

    def _apply_style(self):
        active = "background-color: #0078D4; color: #fff; border: none; font-weight: bold;"
        inactive = "background-color: palette(button); color: palette(button-text); border: none;"
        radius_left = "border-top-left-radius: 4px; border-bottom-left-radius: 4px;"
        radius_right = "border-top-right-radius: 4px; border-bottom-right-radius: 4px;"
        self._light_btn.setStyleSheet(f"QPushButton {{ {active if not self._dark else inactive} {radius_left} }}")
        self._dark_btn.setStyleSheet(f"QPushButton {{ {active if self._dark else inactive} {radius_right} }}")

    def set_dark(self, dark):
        if dark != self._dark:
            self._dark = dark
            self._apply_style()

    def is_dark(self):
        return self._dark

