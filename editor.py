

"""Main SRT/transcript editor window for CapsQual."""
import sys
import re
import json
import os
import math
import tempfile
import webbrowser
from pathlib import Path
from datetime import datetime
from collections import deque
import queue
import threading
import string
import time
import copy

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QTextEdit, QListWidget, QPushButton, QWidget, QLabel,
    QFileDialog, QMessageBox, QSpinBox, QShortcut, QFrame,
    QInputDialog, QLineEdit, QDialog, QDialogButtonBox,
    QGridLayout, QPlainTextEdit, QCheckBox, QTabWidget, QRadioButton,
    QSlider, QProgressBar, QMenuBar, QMenu, QAction, QFontDialog,
    QGroupBox, QScrollArea, QSizePolicy, QComboBox, QStackedWidget, QStyle, QSplashScreen, QSplitter, QSplitterHandle, QToolButton
)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QPoint, QRect, QElapsedTimer, QThread, QSize, QRegularExpression, QSettings
from PyQt5.QtGui import QFont, QKeySequence, QColor, QPalette, QTextCharFormat, QTextCursor, QIcon, QPixmap

from utils import resource_path, logger
from generators import (
    time_to_seconds, time_to_ms, format_timestamp, get_timestamp_width,
    format_srt_time,
    replace_indent_placeholders, generate_gat2_text, generate_dresing_pehl_text,
    generate_tiq_text, generate_srt_text, generate_transcript_text,
    _build_ordered_segments, _group_into_turns, _tokenize_with_pauses,
    _tokenize_cjk_with_pauses, _wrap_text as wrap_text, estimate_missing_timestamps,
    _ms_to_time as ms_to_time
)
from export import (
    build_html_content, write_html_file, write_srt_file, write_txt_file,
    write_docx_file
)

from transcript import Transcript
from parsers import parse_srt, parse_text, parse_tsv, parse_json, parse_vtt
from highlighting import FormattingMarkerHighlighter
from audio_players import SimpleAudioPlayer, VlcAudioPlayer, has_pyaudio
from dialogs import (
    TextSelectionDialog, BlockSplitDialog, EnhancedSymbolDialog, CommentDialog,
    RichEditDialog, EditTimestampsDialog, SettingsDialog, ProjectMemoDialog, JsonImportDialog,
    UnassignedSegmentsDialog, ExportPreviewDialog, SearchDialog, JumpToTimeDialog,
    EnhancedPlacementDialog, PlacementDialog, InsertPausesDialog
)
from widgets import SpeedKnob, WaveformViewer

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
            self.toggle_btn.setText("◀")   # arrow left (expand)
        else:
            self.toggle_btn.setText("▶")   # arrow right (collapse)
    
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
                # Save the size before collapse? Actually we want to restore later.
                # But when manually collapsing, we don't have a saved size.
                # We'll only save size when collapsing via button.
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
    

class SRTEditor(QMainWindow):
    # Constant for placeholder character (visible in viewer)
    INDENT_PLACEHOLDER = '␣'  # U+2423 OPEN BOX — kept for backward compat

    # ── transcript-backed properties ──────────────────────────
    @property
    def srt_blocks(self):
        return self.transcript.blocks

    @srt_blocks.setter
    def srt_blocks(self, value):
        self.transcript.blocks = value

    @property
    def speakers(self):
        return self.transcript.speakers

    @speakers.setter
    def speakers(self, value):
        self.transcript.speakers = value

    @property
    def cjk_mode(self):
        return self.transcript.cjk_mode

    @cjk_mode.setter
    def cjk_mode(self, value):
        self.transcript.cjk_mode = value

    @property
    def file_has_timestamps(self):
        return self.transcript.file_has_timestamps

    @file_has_timestamps.setter
    def file_has_timestamps(self, value):
        self.transcript.file_has_timestamps = value

    def __init__(self, splash=None):
        super().__init__()
        self.splash = splash
        self.transcript = Transcript()
        self.current_block_index = 0

        self.recent_files = []
        self.max_recent = 10
        self.load_recent_files()

        self.undo_stack = []
        self.redo_stack = []
        self.max_undo = 100

        self.context_blocks = 5
        self.current_file_path = None
        self.timestamp_style = "curly"
        self.custom_timestamp_pattern = "{HH:mm:ss}"
        self.audio_file_path = None
        self.project_name = ""
        self.project_memo = ""
        self.text_display_font = QFont("Arial", 12)
        self.has_unsaved_changes = False
        # Load theme from global preferences (QSettings), not from projects
        theme_settings = QSettings('CapsQual', 'Preferences')
        self.current_theme = theme_settings.value('viewer_theme', 'light')
        # Set initial theme palette so all widgets inherit theme colours
        QApplication.instance().setPalette(
            self._dark_palette() if self.current_theme == "dark" else self._light_palette()
        )

        # Set up speaker colour palette based on loaded theme (before init_ui creates widgets)
        if self.current_theme == "dark":
            self.speaker_color_palette = [
                QColor(80, 120, 160),   # Steel blue
                QColor(170, 80, 80),    # Brick red
                QColor(75, 155, 75),    # Forest green
                QColor(170, 170, 80),   # Olive yellow
                QColor(130, 80, 170),   # Amethyst
                QColor(175, 110, 60),   # Burnt orange
                QColor(65, 130, 130),   # Teal
                QColor(170, 80, 120)    # Rose
            ]
        else:
            self.speaker_color_palette = [
                QColor(220, 240, 255),  # Light blue
                QColor(255, 220, 220),  # Light red
                QColor(220, 255, 220),  # Light green
                QColor(255, 255, 200),  # Light yellow
                QColor(230, 200, 255),  # Light purple
                QColor(255, 200, 150),  # Light orange
                QColor(200, 230, 230),  # Light cyan
                QColor(255, 210, 230)   # Light pink
            ]

        # Initialize speaker colors from palette
        self.speaker_colors = self.speaker_color_palette[:4]
        self.playback_speed = 1.0
        self.segment_sync_buffer = 0
        self.original_audio_duration = 0
        self.last_symbol_category = 0

        # VLC audio player
        self.audio_player = None
        self.is_playing = False
        self.auto_sync_enabled = False
        self.auto_pause_enabled = False

        # Timer for UI updates
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.update_ui)
        self.ui_update_timer.start(50)

        self.update_splash("Creating user interface...")
        self.init_ui()

        # Fix up export button style for dark theme (init_ui hardcodes light)
        if self.current_theme == "dark" and hasattr(self, 'btn_quick_export'):
            self.btn_quick_export.setStyleSheet("""
                QPushButton {
                    background-color: #1e7230;
                    padding: 2px 7px;
                    font-size: 12px;
                    font-weight: bold;
                    color: white;
                    border: 0px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #2d9e45;
                }
            """)
    
    def time_label_clicked(self, event):
        self.jump_to_time()
    
    def update_splash(self, message):
        """Update splash screen message if splash exists."""
        if self.splash:
            self.splash.showMessage(message, Qt.AlignBottom | Qt.AlignCenter, Qt.black)
            QApplication.processEvents()  # ensure UI updates
            
        self.marker_pattern = re.compile(r'(#@[BIU]|#@/[BIU])')
        self.punctuation_set = set(string.punctuation + "，。！？；：“”‘’（）【】《》……——·")
        
    def _apply_to_text_ignoring_markers(self, text, func):
        """Apply function `func` to all non‑marker parts of `text`, leaving markers unchanged."""
        parts = []
        last_end = 0
        for m in self.marker_pattern.finditer(text):
            start, end = m.span()
            if start > last_end:
                # Apply func to the non‑marker part
                parts.append(func(text[last_end:start]))
            parts.append(m.group())   # marker remains unchanged
            last_end = end
        if last_end < len(text):
            parts.append(func(text[last_end:]))
        return ''.join(parts)

    def strip_punctuation(self):
        """Remove all punctuation marks from the transcript text (ignoring formatting markers)."""
        if not self.srt_blocks:
            return

        reply = QMessageBox.warning(
            self,
            "Strip Punctuation",
            "This will remove all punctuation marks from the transcript text.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.push_undo()

        def remove_punct(s):
            return ''.join(ch for ch in s if ch not in self.punctuation_set)

        for block in self.srt_blocks:
            block['raw_text'] = self._apply_to_text_ignoring_markers(block['raw_text'], remove_punct)
            block['text'] = block['raw_text']

        self.update_display()
        self.mark_unsaved_changes()
        
    
    def convert_to_lowercase(self):
        """Convert all transcript text to lowercase (ignoring formatting markers)."""
        if not self.srt_blocks:
            return

        reply = QMessageBox.warning(
            self,
            "Convert to Lowercase",
            "This will convert the entire transcript text to lowercase.\n\n"
            "For non Latin‑based transcripts, this may have no effect.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.push_undo()

        for block in self.srt_blocks:
            block['raw_text'] = self._apply_to_text_ignoring_markers(block['raw_text'], str.lower)
            block['text'] = block['raw_text']

        self.update_display()
        self.mark_unsaved_changes()
        
    def init_ui(self):
        self.setWindowTitle("CapsQual 1.6.1 - Subtitle-to-Transcript Workstation")
        # Get the screen geometry (available space, excluding taskbars/docks)
        screen = QApplication.primaryScreen()
        screen_geom = screen.availableGeometry()
        screen_width = screen_geom.width()
        screen_height = screen_geom.height()

        # Set a reasonable initial size (e.g., 80% of width, 90% of height)
        init_width = int(screen_width * 0.8)
        init_height = int(screen_height * 0.9)
        self.resize(init_width, init_height)

        # Set a minimum size that is still usable
        self.setMinimumSize(800, 560)

        # Center the window on the screen
        self.move((screen_width - init_width) // 2, (screen_height - init_height) // 2)

        # Now show the window (do not call showMaximized unless desired)
        self.show()
        self.setWindowIcon(QIcon(resource_path('images/logo.ico')))
        
        # Create menu bar
        self.update_splash("Creating menu bar...")
        self.create_menu_bar()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        
        # Left panel - Context display
        left_panel = QVBoxLayout()
        
        # Current block info display
        self.current_info_label = QLabel("No block selected")
        self.current_info_label.setStyleSheet("""
            QLabel {
                background-color: palette(window);
                color: palette(windowtext);
                padding: 10px;
                border: 2px solid palette(mid);
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        left_panel.addWidget(self.current_info_label)
        
        # Main content display label
        context_label = QLabel("Transcript Content:")
        context_label.setFont(QFont("Arial", 10, QFont.Bold))
        left_panel.addWidget(context_label)
        
        # Main text display
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setFont(self.text_display_font)
        self.text_display.setStyleSheet("""
            QTextEdit {
                background-color: palette(base);
                color: palette(text);
                border: 2px solid palette(mid);
                border-radius: 5px;
                padding: 10px;
            }
        """)
        self.text_display.setMinimumWidth(150)   # allow it to shrink
        self.text_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # horizontal scroll if needed
        left_panel.addWidget(self.text_display)
        self.highlighter = FormattingMarkerHighlighter(self.text_display.document())
        
        # ── Waveform viewer ──────────────────────────────────────
        waveform_label = QLabel("Waveform:")
        waveform_label.setFont(QFont("Arial", 10, QFont.Bold))
        left_panel.addWidget(waveform_label)

        self.waveform_viewer = WaveformViewer()
        self.waveform_viewer.set_theme(self.current_theme)
        self.waveform_viewer.segment_start_changed.connect(self._on_waveform_start_changed)
        self.waveform_viewer.segment_end_changed.connect(self._on_waveform_end_changed)
        self.waveform_viewer.seek_requested.connect(self._on_waveform_seek)
        left_panel.addWidget(self.waveform_viewer)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.btn_prev = QPushButton("← Previous (P)")
        self.btn_prev.clicked.connect(self.previous_block)
        
        self.lbl_current = QLabel("Current: -/-")
        
        self.btn_next = QPushButton("Next (N) →")
        self.btn_next.clicked.connect(self.next_block)
        
      
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_current)
        nav_layout.addWidget(self.btn_next)     
        left_panel.addLayout(nav_layout)
        
        # Right panel - Controls
        right_panel = QVBoxLayout()
        

        # ----- Speaker Assignment group -----
        speaker_group = QGroupBox("Speakers")
        speaker_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        speaker_group_layout = QVBoxLayout()
        speaker_group_layout.setSpacing(2)
        speaker_group_layout.setContentsMargins(0, 0, 0, 0)

        # Header with +/- buttons and count (centered)
        header_layout = QHBoxLayout()
        header_layout.addStretch()

        # Minus button
        self.btn_remove_speaker = QPushButton("−")
        self.btn_remove_speaker.setFixedSize(25, 25)
        self.btn_remove_speaker.setStyleSheet("""
            QPushButton {
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
        """)
        self.btn_remove_speaker.clicked.connect(self.decrease_speaker_count)
        header_layout.addWidget(self.btn_remove_speaker)

        # Speaker count display
        self.speaker_count_label = QLabel("4")
        self.speaker_count_label.setFixedSize(40, 28)
        self.speaker_count_label.setAlignment(Qt.AlignCenter)
        self.speaker_count_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self.speaker_count_label)

        # Plus button
        self.btn_add_speaker = QPushButton("+")
        self.btn_add_speaker.setFixedSize(25, 25)
        self.btn_add_speaker.setStyleSheet(self.btn_remove_speaker.styleSheet())
        self.btn_add_speaker.clicked.connect(self.increase_speaker_count)
        header_layout.addWidget(self.btn_add_speaker)
        header_layout.addStretch()
        speaker_group_layout.addLayout(header_layout)

        # Speaker container (list of speaker widgets)
        self.speaker_container = QWidget()
        self.speaker_layout = QVBoxLayout(self.speaker_container)
        self.speaker_layout.setSpacing(2)
        self.speaker_layout.setContentsMargins(0, 0, 0, 0)
        self.create_speaker_widgets()

        # Wrap speaker container in a scroll area
        speaker_scroll = QScrollArea()
        speaker_scroll.setWidgetResizable(True)
        speaker_scroll.setWidget(self.speaker_container)
        speaker_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        speaker_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        speaker_scroll.setMinimumHeight(70)
        speaker_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)   # allow expansion
        speaker_scroll.setFrameShape(QScrollArea.NoFrame)          # removes the border
        speaker_scroll.setStyleSheet("QScrollArea { border: none; }")  # extra safety

        speaker_group_layout.addWidget(speaker_scroll)
        speaker_group.setLayout(speaker_group_layout)
        right_panel.addWidget(speaker_group)
        
         # Audio controls group
        audio_group = QGroupBox("Audio Controls")
        audio_group.setMaximumHeight(240)
        audio_layout = QVBoxLayout()
        audio_layout.setSpacing(2)
        audio_layout.setContentsMargins(3, 3, 3, 3)
        # Audio file info
        self.audio_info_label = QLabel("No audio loaded")
        self.audio_info_label.setStyleSheet("""
            QLabel {
                padding: 0px; 
                border-radius: 3px;
                font-size: 11px;
            }
        """)
        self.audio_info_label.setMinimumWidth(170)
        audio_layout.addWidget(self.audio_info_label)

        # Audio progress bar
        self.audio_progress = QSlider(Qt.Horizontal)
        self.audio_progress.setEnabled(False)
        self.audio_progress.sliderMoved.connect(self.seek_audio)
        self.audio_progress.setStyleSheet("""
            QSlider {
                padding: 0px;
                margin: 0px;
            }
        """)
        audio_layout.addWidget(self.audio_progress)

        # Time display
        time_layout = QHBoxLayout()
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setCursor(Qt.PointingHandCursor)
        self.time_label.setToolTip("Click to jump to time (Ctrl+J)")
        self.time_label.mousePressEvent = self.time_label_clicked
        audio_button_font = QFont("Segoe UI Symbol")
                              
        self.btn_play_segment = QPushButton("Play from segment (Shift+Enter)")
        self.btn_play_segment.clicked.connect(self.play_from_current_segment)
        self.btn_play_segment.setEnabled(False)  # initially disabled until audio loaded
        self.btn_play_segment.setToolTip("Play audio from the start of the current segment")
        
        time_layout.addWidget(self.time_label)
        time_layout.addWidget(self.btn_play_segment)
        audio_layout.addLayout(time_layout)

        # Audio controls
        audio_controls_layout = QHBoxLayout()
        audio_controls_layout.setSpacing(15)

        self.btn_load_audio = QPushButton("Load Audio")
        self.btn_load_audio.clicked.connect(self.load_audio_file)
        
        self.btn_rewind = QPushButton("⏪ (PgUp)")
        self.btn_rewind.clicked.connect(self.rewind_audio)
        self.btn_rewind.setFont(audio_button_font)
        self.btn_rewind.setEnabled(False)

        self.btn_play = QPushButton("▶ (End)")
        self.btn_play.clicked.connect(self.toggle_playback)
        self.btn_play.setFont(audio_button_font)
        self.btn_play.setEnabled(False)

        self.btn_forward = QPushButton("⏩ (PgDn)")
        self.btn_forward.clicked.connect(self.forward_audio)
        self.btn_forward.setFont(audio_button_font)
        self.btn_forward.setEnabled(False)
        

        audio_controls_layout.addWidget(self.btn_load_audio)
        audio_controls_layout.addWidget(self.btn_rewind)
        audio_controls_layout.addWidget(self.btn_play)
        audio_controls_layout.addWidget(self.btn_forward)

        audio_layout.addLayout(audio_controls_layout)
    

        # Auto-sync and Autopause checkboxes
        sync_layout = QHBoxLayout()
        self.auto_sync_check = QCheckBox("Auto-sync to audio")
        self.auto_sync_check.setEnabled(False)
        self.auto_sync_check.setChecked(False)
        self.auto_sync_check.toggled.connect(self.toggle_auto_sync)

        self.auto_pause_check = QCheckBox("Autopause during editing")
        self.auto_pause_check.setEnabled(False)
        self.auto_pause_check.setChecked(False)
        self.auto_pause_check.toggled.connect(self.toggle_auto_pause)

        sync_layout.addWidget(self.auto_sync_check)
        sync_layout.addWidget(self.auto_pause_check)
        sync_layout.addStretch()

        audio_layout.addLayout(sync_layout)
        
        # Speed control
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(15)
        speed_layout.addWidget(QLabel("Playback Speed:"))

        self.speed_slower_btn = QPushButton("-")
        self.speed_slower_btn.clicked.connect(lambda: self.speed_knob.set_value_direct(max(0.5, self.playback_speed - 0.1)))
        self.speed_slower_btn.setFixedWidth(30)
        speed_layout.addWidget(self.speed_slower_btn)

        self.speed_knob = SpeedKnob()
        self.speed_knob.valueChanged.connect(self.change_playback_speed)
        #self.speed_knob.setMinimumHeight(40)
        self.speed_knob.setMinimumSize(30, 30)   # allow very small (will be drawn scaled)
        
        # Create a container widget for the speed knob with a fixed height
        knob_container = QWidget()
        knob_container.setMinimumHeight(30)
        knob_container.setMaximumHeight(60)  # or whatever maximum height you want
        knob_layout = QVBoxLayout(knob_container)
        knob_layout.setContentsMargins(0, 0, 0, 0)
        
        knob_layout.addWidget(self.speed_knob)
        knob_layout.setAlignment(Qt.AlignCenter)  # center the knob vertically

        # Then add the container to speed_layout instead of the knob directly
        speed_layout.addWidget(knob_container)
        #audio_layout.addStretch()

        self.speed_normal_btn = QPushButton("Reset")
        self.speed_normal_btn.clicked.connect(lambda: self.speed_knob.set_value_direct(1.0))
        self.speed_normal_btn.setFixedWidth(60)

        self.speed_faster_btn = QPushButton("+")
        self.speed_faster_btn.clicked.connect(lambda: self.speed_knob.set_value_direct(min(2.0, self.playback_speed + 0.1)))
        self.speed_faster_btn.setFixedWidth(30)

        speed_layout.addWidget(self.speed_faster_btn)
        speed_layout.addWidget(self.speed_normal_btn)

        # Add directly to audio_layout (no container)
        audio_layout.addLayout(speed_layout)

        audio_group.setLayout(audio_layout)
        right_panel.addWidget(audio_group)
        
        
        # Button panel (split, merge, edit, etc.)
        button_panel = QGroupBox()
        button_layout = QVBoxLayout()

        # First row: Split, Merge, Edit
        row1 = QHBoxLayout()
        self.btn_split = QPushButton("Split (Space)")
        self.btn_merge = QPushButton("Merge (Del)")
        self.btn_edit = QPushButton("Edit (E)")
        row1.addWidget(self.btn_split)
        row1.addWidget(self.btn_merge)
        row1.addWidget(self.btn_edit)
        button_layout.addLayout(row1)

        # Second row: Edit Timestamp, Unassign, Symbols
        row2 = QHBoxLayout()
        self.btn_edit_time = QPushButton("Edit Timestamp (T)")
        self.btn_unassign = QPushButton("Unassign (U)")
        self.btn_symbols = QPushButton("Symbols (*)")
        row2.addWidget(self.btn_edit_time)
        row2.addWidget(self.btn_unassign)
        row2.addWidget(self.btn_symbols)
        button_layout.addLayout(row2)
        
        self.btn_split.clicked.connect(self.split_current_block)
        self.btn_merge.clicked.connect(self.merge_with_next)
        self.btn_edit.clicked.connect(self.edit_current_block)
        self.btn_edit_time.clicked.connect(self.edit_current_timestamps)
        self.btn_unassign.clicked.connect(self.unassign_current)
        self.btn_symbols.clicked.connect(self.open_pause_dialog)
        button_panel.setLayout(button_layout)
        right_panel.addWidget(button_panel)
        
        
        # Unassigned blocks with counter
        self.unassigned_blocks_label = QLabel("Unassigned Segments (0/0):")
        #self.unassigned_blocks_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(self.unassigned_blocks_label)

        self.unassigned_list = QListWidget()
        self.unassigned_list.setMinimumHeight(40)
        self.unassigned_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.unassigned_list.itemDoubleClicked.connect(self.jump_to_block)
        
        right_panel.addWidget(self.unassigned_list)  # Give it stretch factor 1 to expand

        # Button container (will stay at bottom)
        button_container = QWidget()
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(5)

        self.btn_quick_export = QPushButton(" Export Transcript (Ctrl+Enter)")
        self.btn_quick_export.clicked.connect(self.export_transcript)
        svg_data = b'''<svg width="48" height="48" viewBox="0 0 600 500" xmlns="http://www.w3.org/2000/svg">
          <path d="m171,183l-94,0l0,227l397,0l0,-50" fill="none" stroke="#ffffff" stroke-width="13" transform="matrix(0.951576, 0, 0, 0.792082, 22.341, 67.1476)"/>
          <path d="m442.89,147.05l0.11,-76.05l114,118l-111,110l0,-69l-104.18,5.12c-29.52,4.98 -61.24,13.64 -106.76,43.52c-20.93,14.7 -31.06,17.82 -55.47,47c2.24,-13 10.61,-52.7 30.2,-83.17c35.09,-46.28 65.11,-63.01 74.11,-67.01c41.62,-30.5 165,-26.41 159,-28.41z" fill="none" stroke="#ffffff" stroke-width="13"/>
        </svg>'''
        pixmap = QPixmap()
        pixmap.loadFromData(svg_data)
        icon = QIcon(pixmap)
        self.btn_quick_export.setIcon(icon)
        self.btn_quick_export.setIconSize(QSize(32, 32))
        self.btn_quick_export.setStyleSheet("""
            QPushButton {
                background-color: #124607;
                padding: 2px 7px;
                font-size: 12px;
                font-weight: bold;
                color: white;
                border: 0px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #71906a;
            }
        """)
        button_layout.addWidget(self.btn_quick_export)
        
        right_panel.addWidget(button_container)  # No stretch, stays at bottom
        
        
        # Create left and right panel widgets
        left_widget = QWidget()
        left_widget.setLayout(left_panel)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setMinimumWidth(0)
        right_widget.setMaximumWidth(450)   # optional, adjust as needed

        # Create custom splitter
        splitter = CollapsibleSplitter(Qt.Horizontal, right_widget)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([800, 200])   # initial sizes
        splitter.setHandleWidth(15)     # wider handle for button

        # Add splitter to central layout
        layout.addWidget(splitter)
        
        self.update_splash("Setting up shortcuts...")
        self.setup_shortcuts()
        # Apply initial theme QSS (buttons, scrollbars, group boxes, labels)
        self._apply_theme_qss()
    
    def preload_modules(self):
        """Preload heavy audio modules while splash is still visible."""
        # These imports will happen now, while splash is up
        try:
            import pyaudio
            import soundfile
            import numpy
        except ImportError:
            pass

    def load_recent_files(self):
        settings = QSettings('CapsQual', 'RecentFiles')
        size = settings.beginReadArray('recent')
        self.recent_files = []
        for i in range(size):
            settings.setArrayIndex(i)
            path = settings.value('path')
            print(f"load_recent_files: index {i}, path={repr(path)}")
            if path and os.path.exists(path):
                self.recent_files.append(path)
            else:
                print(f"  -> skipping (exists={os.path.exists(path) if path else False})")
        settings.endArray()
        print(f"Recent files after load: {self.recent_files}")

    def save_recent_files(self):
        """Save recent files list to QSettings."""
        settings = QSettings('CapsQual', 'RecentFiles')
        settings.beginWriteArray('recent')
        for i, path in enumerate(self.recent_files):
            settings.setArrayIndex(i)
            settings.setValue('path', path)
        settings.endArray()

    def add_to_recent(self, filepath):
        print(f"add_to_recent: adding {repr(filepath)}")
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)
        self.recent_files.insert(0, filepath)
        if len(self.recent_files) > self.max_recent:
            self.recent_files.pop()
        self.save_recent_files()
        print(f"Recent files now: {self.recent_files}")

    def update_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            action = self.recent_menu.addAction("(empty)")
            action.setEnabled(False)
        else:
            for path in self.recent_files:
                name = os.path.basename(path)
                action = self.recent_menu.addAction(name)
                # Use lambda with default argument to capture path
                action.triggered.connect(lambda checked, p=path: self.open_recent_file(p))
            self.recent_menu.addSeparator()
            clear_action = self.recent_menu.addAction("Clear Recent")
            clear_action.triggered.connect(self.clear_recent)

    def clear_recent(self):
        """Clear the recent files list."""
        self.recent_files = []
        self.save_recent_files()
        self.update_recent_menu()  # immediate update (menu is about to be shown anyway)

    def open_recent_file(self, path):
        """Open a file from the recent list."""
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found",
                                f"The file '{path}' does not exist.\nIt will be removed from the recent list.")
            self.recent_files.remove(path)
            self.save_recent_files()
            return
        if self.check_unsaved_changes():
            ext = os.path.splitext(path)[1].lower()
            if ext in ('.capsqual', '.capsgat'):
                self.load_project_from_path(path)
            else:
                self.load_file_from_path(path)
               
                
    def push_undo(self):
        """Save current state before a modification."""
        state = {
            'blocks': copy.deepcopy(self.srt_blocks),
            'current_index': self.current_block_index,
            'speakers': self.speakers.copy()
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)
        self.update_undo_redo_actions()

    def undo(self):
        if not self.undo_stack:
            return
        # push current state to redo
        current = {
            'blocks': copy.deepcopy(self.srt_blocks),
            'current_index': self.current_block_index,
            'speakers': self.speakers.copy()
        }
        self.redo_stack.append(current)
        # restore previous state
        prev = self.undo_stack.pop()
        self._restore_state(prev)
        self.update_undo_redo_actions()

    def redo(self):
        if not self.redo_stack:
            return
        # push current state to undo
        current = {
            'blocks': copy.deepcopy(self.srt_blocks),
            'current_index': self.current_block_index,
            'speakers': self.speakers.copy()
        }
        self.undo_stack.append(current)
        # restore next state
        next_state = self.redo_stack.pop()
        self._restore_state(next_state)
        self.update_undo_redo_actions()

    def _restore_state(self, state):
        """Restore a saved state and refresh the UI."""
        self.srt_blocks = state['blocks']
        self.current_block_index = state['current_index']
        self.speakers = state['speakers']
        self.speaker_count_label.setText(str(len(self.speakers)))
        self.update_display()
        self.create_speaker_widgets()
        self.setup_shortcuts()
        self.update_speaker_buttons()
        self.mark_unsaved_changes()

    def update_undo_redo_actions(self):
        """Enable/disable Undo/Redo menu items based on stack emptiness."""
        if hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(len(self.undo_stack) > 0)
        if hasattr(self, 'redo_action'):
            self.redo_action.setEnabled(len(self.redo_stack) > 0)
            
        
    def insert_pauses_for_gaps(self):
        if not self.srt_blocks or len(self.srt_blocks) < 2:
            QMessageBox.information(self, "Cannot Insert Pauses",
                "Need at least two segments to calculate gaps.")
            return

        # Check if we have timestamps
        has_any_timestamp = any(block.get('start_time') for block in self.srt_blocks)
        if not has_any_timestamp:
            QMessageBox.warning(self, "No Timestamps",
                "This transcript does not contain timestamp information.\n\n"
                "Pause insertion requires start and end times for segments.")
            return

        dialog = InsertPausesDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return

        settings = dialog.get_settings()
        convention = settings['convention']
        use_measured = settings['use_measured']
        measured_threshold = settings['measured_threshold']
        min_gap = settings['min_gap']
        mode = settings['mode']
        threshold = settings['threshold']  # used only if mode == "threshold"

        self.push_undo()

        blocks = self.srt_blocks
        inserted_count = 0

        # Work from last to first to avoid index shifting when inserting new blocks
        for i in range(len(blocks) - 2, -1, -1):
            current = blocks[i]
            nxt = blocks[i+1]

            # Get end time of current and start time of next
            if not current.get('end_time') or not nxt.get('start_time'):
                continue

            end_sec = time_to_seconds(current['end_time'])
            start_sec = time_to_seconds(nxt['start_time'])
            gap = start_sec - end_sec

            if gap < min_gap:
                continue

            # Generate pause symbol
            symbol = self.gap_to_pause_symbol(gap, convention, use_measured, measured_threshold)
            if not symbol:
                continue

            # Decide action based on mode
            separate_this = False
            if mode == "separate":
                separate_this = True
            elif mode == "attach":
                separate_this = False
            else:  # threshold
                separate_this = (gap >= threshold)

            if separate_this:
                # Insert a new pause block after current
                new_block = {
                    'index': max(b['index'] for b in blocks) + 1,
                    'start_time': current['end_time'],
                    'end_time': nxt['start_time'],
                    'text': symbol,
                    'raw_text': symbol,
                    'speaker': None,
                    'is_turn_start': False,
                    'is_pause': True,
                }
                blocks.insert(i+1, new_block)
                inserted_count += 1
            else:
                # Prepend symbol to the next block's text (no timestamp change)
                if self.cjk_mode:
                    prefix = symbol
                else:
                    # Add a space after the symbol unless the next block already starts with space
                    if nxt['raw_text'] and not nxt['raw_text'][0].isspace():
                        prefix = symbol + " "
                    else:
                        prefix = symbol
                nxt['raw_text'] = prefix + nxt['raw_text']
                nxt['text'] = nxt['raw_text']
                inserted_count += 1   # still count as a pause inserted

        if inserted_count > 0:
            self.update_display()
            self.mark_unsaved_changes()
            QMessageBox.information(self, "Pauses Inserted",
                f"Inserted {inserted_count} pause(s).")
        else:
            QMessageBox.information(self, "No Pauses",
                "No gaps meeting the criteria were found.")
        
    def gap_to_pause_symbol(self, gap_seconds, convention, use_measured, measured_threshold):
        """Return the appropriate pause symbol for the given gap and convention."""
        if convention == "gat2":
            if gap_seconds < 0.2:
                return "(.)"
            elif gap_seconds < 0.5:
                return "(-)"
            elif gap_seconds < 0.8:
                return "(--)"
            elif gap_seconds < 1.0:
                return "(---)"
            else:
                if use_measured and gap_seconds >= measured_threshold:
                    # GAT2 measured pauses: one decimal
                    return f"({gap_seconds:.1f})"
                else:
                    return "(---)"
        elif convention == "dresing_pehl":
            if gap_seconds < 1:
                return "(.)"
            elif gap_seconds < 2:
                return "(..)"
            elif gap_seconds < 3:
                return "(...)"
            else:
                if use_measured and gap_seconds >= measured_threshold:
                    # Dresing & Pehl measured pauses: whole seconds (rounded)
                    return f"({int(round(gap_seconds))})"
                else:
                    return "(...)"
        elif convention == "tiq":
            if gap_seconds < 1.0:
                return "(.)"
            else:
                if use_measured and gap_seconds >= measured_threshold:
                    # TiQ measured pauses: whole seconds (rounded)
                    return f"({int(round(gap_seconds))})"
                else:
                    # For TiQ, non‑measured pauses remain short
                    return "(.)"
        else:
            return None
                
                
        
    
    def count_leading_spaces(self, s):
        """Return number of leading space characters."""
        return len(s) - len(s.lstrip(' '))
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        new_project_action = QAction('New Project', self)
        new_project_action.setShortcut('Ctrl+N')
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)
        
        open_project_action = QAction('Open Project...', self)
        open_project_action.setShortcut('Ctrl+O')
        open_project_action.triggered.connect(self.load_project)
        file_menu.addAction(open_project_action)
        
        self.recent_menu = QMenu('Open Recent', self)
        file_menu.addMenu(self.recent_menu)
        self.recent_menu.aboutToShow.connect(self.update_recent_menu)
        
        save_project_action = QAction('Save Project', self)
        save_project_action.setShortcut('Ctrl+S')
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        
        save_as_action = QAction('Save Project As...', self)
        save_as_action.triggered.connect(lambda: self.save_project(force_save_as=True))
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # Import submenu
        import_menu = file_menu.addMenu('Import')
        
        import_subtitles_action = QAction('Subtitles...', self)
        import_subtitles_action.triggered.connect(self.import_subtitles)
        import_menu.addAction(import_subtitles_action)
        
        import_audio_action = QAction('Audio File...', self)
        import_audio_action.triggered.connect(self.load_audio_file)
        import_menu.addAction(import_audio_action)
        
        # Export
        export_action = QAction('Export...', self)
        export_action.setShortcut('Ctrl+Return')
        export_action.triggered.connect(self.export_transcript)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu('Edit')
        self.undo_action = QAction('Undo', self)
        self.undo_action.setShortcut('Ctrl+Z')
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction('Redo', self)
        self.redo_action.setShortcut('Ctrl+Y')   # also Ctrl+Shift+Z on some systems
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        
        # Modify transcript submenu
        modify_menu = edit_menu.addMenu('Modify transcript')
        
        insert_pauses_action = QAction('Insert pause symbols for gaps…', self)
        insert_pauses_action.triggered.connect(self.insert_pauses_for_gaps)
        self.insert_pauses_action = insert_pauses_action
        modify_menu.addAction(insert_pauses_action)
        
        strip_punct_action = QAction('Strip punctuation', self)
        strip_punct_action.triggered.connect(self.strip_punctuation)
        modify_menu.addAction(strip_punct_action)

        lowercase_action = QAction('Convert to lowercase', self)
        lowercase_action.triggered.connect(self.convert_to_lowercase)
        modify_menu.addAction(lowercase_action)
        
                
        search_action = QAction('Search...', self)
        search_action.triggered.connect(self.open_search_dialog)
        edit_menu.addAction(search_action)
        
        settings_action = QAction('Settings...', self)
        settings_action.triggered.connect(self.open_settings)
        edit_menu.addAction(settings_action)
        
        project_memo_action = QAction('Project Memo...', self)
        project_memo_action.triggered.connect(self.open_project_memo)
        edit_menu.addAction(project_memo_action)
        
        custom_menu = edit_menu.addMenu('Custom Symbols')
    
        manage_custom_action = QAction('Manage Custom Symbols...', self)
        manage_custom_action.triggered.connect(self.manage_custom_symbols)
        custom_menu.addAction(manage_custom_action)
          
        custom_menu.addSeparator()
        
        export_custom_action = QAction('Export Custom Symbols...', self)
        export_custom_action.triggered.connect(self.export_custom_symbols)
        custom_menu.addAction(export_custom_action)
        
        import_custom_action = QAction('Import Custom Symbols...', self)
        import_custom_action.triggered.connect(self.import_custom_symbols)
        custom_menu.addAction(import_custom_action)
        self.manage_custom_action = manage_custom_action
        self.export_custom_action = export_custom_action
        self.import_custom_action = import_custom_action
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        shortcuts_action = QAction('Shortcuts', self)
        shortcuts_action.setShortcut('F1')
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        manual_action = QAction('Online Manual', self)
        manual_action.setShortcut('Ctrl+F1')
        manual_action.triggered.connect(self.open_manual)
        help_menu.addAction(manual_action)
        
        about_action = QAction('About CapsQual', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def update_menu_state(self):
        """Enable/disable custom symbol menu items based on transcript presence."""
        enabled = bool(self.srt_blocks)
        if hasattr(self, 'manage_custom_action'):
            self.manage_custom_action.setEnabled(enabled)
            self.export_custom_action.setEnabled(enabled)
            self.import_custom_action.setEnabled(enabled)
        
    def manage_custom_symbols(self):
        """Open symbol dialog and switch to Custom tab."""
        if not self.srt_blocks:
            QMessageBox.information(self, "No Transcript",
                "Please load a transcript first to manage custom symbols.")
            return
        dialog = EnhancedSymbolDialog(self)
        # Switch to the last category (Custom)
        dialog.switch_category(len(dialog.categories) - 1)
        if dialog.exec_() == QDialog.Accepted:
            symbol_info = dialog.get_selected_symbol_info()
            self.handle_symbol_insertion(symbol_info)

    def export_custom_symbols(self):
        """Export custom symbols to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Custom Symbols", self._base_dir_for_dialog(),
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(EnhancedSymbolDialog.custom_symbols, f, indent=2)
                QMessageBox.information(self, "Success", f"Custom symbols exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not export: {e}")

    def import_custom_symbols(self):
        """Import custom symbols from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Custom Symbols", self._base_dir_for_dialog(),
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    imported = json.load(f)
                
                if isinstance(imported, list):
                    reply = QMessageBox.question(
                        self, "Merge Symbols",
                        f"Found {len(imported)} symbols. Merge with existing?",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    
                    if reply == QMessageBox.Yes:
                        EnhancedSymbolDialog.custom_symbols.extend(imported)
                    elif reply == QMessageBox.No:
                        EnhancedSymbolDialog.custom_symbols = imported
                    else:
                        return
                    
                    # Save to file
                    with open(EnhancedSymbolDialog.custom_symbols_file, 'w', encoding='utf-8') as f:
                        json.dump(EnhancedSymbolDialog.custom_symbols, f, indent=2)
                    
                    QMessageBox.information(self, "Success", f"Imported {len(imported)} symbols")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not import: {e}")
        
    def increase_speaker_count(self):
        """Increase number of speakers by 1"""
        current = len(self.speakers)
        if current < 8:  # Max 8 speakers
            self.push_undo()
            self.update_speaker_count(current + 1)
            self.speaker_count_label.setText(str(current + 1))
            # Update button states
            self.update_speaker_buttons()

    def decrease_speaker_count(self):
        """Decrease number of speakers by 1"""
        self.push_undo()
        current = len(self.speakers)
        if current <= 2:  # Min 2 speakers
            return
        
        # Check if the last speaker (highest index) has any assigned segments
        last_speaker_idx = current - 1
        assigned_count = self.count_blocks_for_speaker(last_speaker_idx)
        
        if assigned_count > 0:
            # Show warning dialog
            speaker_name = self.speakers[last_speaker_idx]
            reply = QMessageBox.warning(
                self,
                "Remove Speaker",
                f"Speaker {speaker_name} is assigned to {assigned_count} segment(s).\n\n"
                f"Removing this speaker will unassign all these segments.\n\n"
                f"Do you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return  # User canceled
            
            # Unassign all blocks for this speaker
            for block in self.srt_blocks:
                if block.get('speaker') == last_speaker_idx:
                    block['speaker'] = None
                    block['is_turn_start'] = True
            
            self.update_display()
            self.mark_unsaved_changes()
        
        # Now remove the speaker
        self.update_speaker_count(current - 1)

    def update_speaker_buttons(self):
        """Enable/disable speaker buttons based on current count"""
        current = len(self.speakers)
        self.btn_add_speaker.setEnabled(current < 8)
        self.btn_remove_speaker.setEnabled(current > 2)
           
    def setup_shortcuts(self):
        # Clear any existing shortcuts first (to avoid duplicates)
        for shortcut in self.findChildren(QShortcut):
            shortcut.disconnect()
            shortcut.deleteLater()
        
        # Dynamic speaker shortcuts based on current count
        self.speaker_shortcuts = []  # Store shortcuts to prevent garbage collection
        for i in range(len(self.speakers)):
            shortcut = QShortcut(QKeySequence(str(i+1)), self)
            # Use a default argument to capture i, and accept the checked parameter
            shortcut.activated.connect(lambda checked=False, idx=i: self.assign_speaker(idx))
            self.speaker_shortcuts.append(shortcut)
        
        # Navigation shortcuts
        QShortcut(QKeySequence("N"), self).activated.connect(self.next_block)
        QShortcut(QKeySequence("P"), self).activated.connect(self.previous_block)
        QShortcut(QKeySequence("Right"), self).activated.connect(self.next_block)
        QShortcut(QKeySequence("Left"), self).activated.connect(self.previous_block)
        QShortcut(QKeySequence("Space"), self).activated.connect(self.split_current_block)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self.merge_with_next)
        QShortcut(QKeySequence("E"), self).activated.connect(self.edit_current_block)
        QShortcut(QKeySequence("T"), self).activated.connect(self.edit_current_timestamps)
        QShortcut(QKeySequence("F2"), self).activated.connect(self.edit_current_block)
        QShortcut(QKeySequence("*"), self).activated.connect(self.open_pause_dialog)
        QShortcut(QKeySequence("U"), self).activated.connect(self.unassign_current)
        QShortcut(QKeySequence("Ctrl+Del"), self).activated.connect(self.remove_overlap_from_current)

        QShortcut(QKeySequence("Return"), self).activated.connect(self.insert_empty_line)
        QShortcut(QKeySequence("."), self).activated.connect(lambda: self.handle_pause("(.)"))
        QShortcut(QKeySequence("H"), self).activated.connect(lambda: self.handle_pause("°h"))
        QShortcut(QKeySequence("Shift+H"), self).activated.connect(lambda: self.handle_pause("h°"))
        QShortcut(QKeySequence("Shift+Return"), self).activated.connect(self.play_from_current_segment)
        QShortcut(QKeySequence("Shift+Enter"), self).activated.connect(self.play_from_current_segment)  # for numpad Enter
        
        QShortcut(QKeySequence("PgUp"), self).activated.connect(self.rewind_audio)
        QShortcut(QKeySequence("End"), self).activated.connect(self.toggle_playback)
        QShortcut(QKeySequence("PgDown"), self).activated.connect(self.forward_audio)
        QShortcut(QKeySequence("Ctrl+J"), self).activated.connect(self.jump_to_time)
        QShortcut(QKeySequence("Shift+L"), self).activated.connect(
            lambda: self.auto_sync_with_audio(self.audio_player.get_position() if self.audio_player else 0)
        )
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.toggle_auto_sync_shortcut)
               
        QShortcut(QKeySequence("+"), self).activated.connect(lambda: self.speed_knob.set_value_direct(min(2.0, self.playback_speed + 0.1)))
        QShortcut(QKeySequence("-"), self).activated.connect(lambda: self.speed_knob.set_value_direct(max(0.5, self.playback_speed - 0.1)))
        QShortcut(QKeySequence("0"), self).activated.connect(lambda: self.speed_knob.set_value_direct(1.0))
        
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.open_search_dialog)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.find_next)
        QShortcut(QKeySequence("Shift+F3"), self).activated.connect(self.find_previous)
        
        self.update_splash("Loading user interface...")
    



    
    def update_ui(self):
        """Update UI elements based on current state"""
        if self.audio_player:
            current_time = self.audio_player.get_position()
            duration = self.audio_player.duration
            
            if duration > 0:
                # Update progress slider
                self.audio_progress.setValue(int(current_time / duration * 100))
                
                # Update time label
                current_str = f"{int(current_time // 60):02d}:{int(current_time % 60):02d}"
                duration_str = f"{int(duration // 60):02d}:{int(duration % 60):02d}"
                speed_str = f" ({self.playback_speed:.1f}x)" if abs(self.playback_speed - 1.0) > 0.01 else ""
                self.time_label.setText(f"{current_str} / {duration_str}")
                
                # Auto-sync if enabled
                if self.auto_sync_enabled and self.srt_blocks and self.file_has_timestamps:
                    self.auto_sync_with_audio(current_time)
    
    def update_speed_controls_state(self):
        """Enable speed controls only if the current player is a VlcAudioPlayer."""
        if self.audio_player and isinstance(self.audio_player, VlcAudioPlayer):
            self.speed_knob.setEnabled(True)
            self.speed_slower_btn.setEnabled(True)
            self.speed_normal_btn.setEnabled(True)
            self.speed_faster_btn.setEnabled(True)
            self.speed_knob.setToolTip("Adjust playback speed")
        else:
            self.speed_knob.setEnabled(False)
            self.speed_slower_btn.setEnabled(False)
            self.speed_normal_btn.setEnabled(False)
            self.speed_faster_btn.setEnabled(False)
            self.speed_knob.setToolTip("Speed control requires VLC media player")
    
    def load_audio_file(self):
        """Load an audio file using appropriate player"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Audio File", self._base_dir_for_dialog(), 
            "Audio Files (*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma);;All Files (*)"
        )
        
        if not file_path:
            return

        # Check for subtitle files in the same directory
        audio_dir = Path(file_path).parent
        subtitle_files = list(audio_dir.glob("*.srt")) + list(audio_dir.glob("*.json")) + \
                         list(audio_dir.glob("*.txt")) + list(audio_dir.glob("*.tsv"))
        
        if subtitle_files:
            reply = QMessageBox.question(
                self,
                "Subtitle File Found",
                f"Found {len(subtitle_files)} subtitle file(s). Import one?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Yes:
                file_list = [str(f.name) for f in subtitle_files]
                file_name, ok = QInputDialog.getItem(
                    self, "Select Subtitle File", "Choose file:", file_list, 0, False
                )
                if ok and file_name:
                    if self.check_unsaved_changes():
                        subtitle_path = audio_dir / file_name
                        self.current_file_path = str(subtitle_path)
                        self.load_file_from_path(str(subtitle_path))
            elif reply == QMessageBox.Cancel:
                return
        
        # Stop any existing audio
        if self.audio_player:
            self.audio_player.cleanup()
            self.audio_player = None
        
        # Reset speed display
        self.playback_speed = 1.0
        self.speed_knob.value = 1.0
        self.speed_knob.update()
        self.speed_normal_btn.setText("1.0x")
        
        self.update_splash("Loading audio player...")
        
        # Try to create VLC player first
        try:
            self.audio_player = VlcAudioPlayer()
            player_name = "VLC"
            vlc_ok = True
        except Exception as e:
            logger.warning(f"VLC not available: {e}")
            # Fallback to simple player
            if has_pyaudio():
                self.audio_player = SimpleAudioPlayer()
                player_name = "Simple (fallback)"
                vlc_ok = False
            else:
                QMessageBox.warning(self, "No Audio Backend", 
                    "Neither VLC nor PyAudio is available.\n\n"
                    "Please install VLC from https://www.videolan.org/vlc/")
                return
        
        # Connect signals
        self.audio_player.playback_started.connect(self.on_playback_started)
        self.audio_player.playback_stopped.connect(self.on_playback_stopped)
        self.audio_player.position_changed.connect(self.on_position_changed)
        
        if hasattr(self.audio_player, 'playback_paused'):
            self.audio_player.playback_paused.connect(self.on_playback_paused)
        if hasattr(self.audio_player, 'end_reached'):
            self.audio_player.end_reached.connect(self.on_playback_ended)
        
        # Load the file
        if self.audio_player.load_file(file_path):
            self.audio_file_path = file_path
            # Load waveform data for the viewer
            self._load_waveform_audio(file_path)
            audio_name = Path(file_path).name

            # Update status label
            # Update status label            audio_name = Path(file_path).name
            
            # Update status label
            if vlc_ok:
                status = f"Audio loaded: {audio_name}"
            else:
                status = f"Audio loaded: {audio_name} (⚠ VLC not found)"
            self.audio_info_label.setText(status)
            
            # Enable basic controls
            self.btn_play.setEnabled(True)
            self.btn_rewind.setEnabled(True)
            self.btn_forward.setEnabled(True)
            self.btn_play_segment.setEnabled(True)
            self.auto_sync_check.setEnabled(self.file_has_timestamps)
            self.auto_pause_check.setEnabled(True)
            self.audio_progress.setEnabled(True)
            
            # Update speed controls based on player type
            self.update_speed_controls_state()
            
            logger.info(f"Audio loaded with {player_name} player: {audio_name}")
        else:
            QMessageBox.critical(self, "Error", f"Failed to load audio file (Install VLC)")
            self.audio_player = None
            self._clear_waveform_audio()
            self.audio_info_label.setText("No audio loaded")
    
    def toggle_playback(self):
        """Toggle play/pause"""
        if not self.audio_player:
            return
        
        if self.audio_player.is_playing:
            self.audio_player.pause()
            self.btn_play.setText("▶ (End)")
            self.is_playing = False
        else:
            # For fallback player, ensure thread is running
            if isinstance(self.audio_player, SimpleAudioPlayer) and not self.audio_player.isRunning():
                self.audio_player.start()
            
            self.audio_player.play()
            self.btn_play.setText("⏸ (End)")
            self.is_playing = True
            
    def rewind_audio(self):
        """Rewind by 5 seconds"""
        if self.audio_player:
            current_pos = self.audio_player.get_position()
            new_pos = max(0, current_pos - 5)
            self.audio_player.seek(new_pos)
    
    def forward_audio(self):
        """Fast forward by 5 seconds"""
        if self.audio_player:
            current_pos = self.audio_player.get_position()
            duration = self.audio_player.duration
            new_pos = min(duration, current_pos + 5)
            self.audio_player.seek(new_pos)
    
    def seek_audio(self, position_percent):
        """Seek to position"""
        if self.audio_player:
            position_seconds = position_percent / 100.0 * self.audio_player.duration
            self.audio_player.seek(position_seconds)
    
    def jump_to_time(self):
        """Jump to specific time"""
        if self.audio_player and self.audio_player.duration > 0:
            max_duration = self.audio_player.duration
            dialog = JumpToTimeDialog(int(max_duration * 1000), self)
            if dialog.exec_() == QDialog.Accepted:
                target_time_ms = dialog.get_target_time()
                self.audio_player.seek(target_time_ms / 1000.0)
                
    def play_from_current_segment(self):
        """Seek audio to the start of the current transcript block and play."""
        if not self.audio_player:
            QMessageBox.information(self, "No Audio", "No audio file loaded.")
            return

        if not self.srt_blocks:
            return

        block = self.srt_blocks[self.current_block_index]
        if not block.get('start_time'):
            QMessageBox.information(self, "No Timestamp",
                "The current segment does not have a start time.")
            return

        # Convert start_time to seconds
        seconds = time_to_seconds(block['start_time'])

        # If already playing, just seek. If not, play then seek so the first time
        # after load the seek takes effect (some backends only apply seek after play has started).
        if self.audio_player.is_playing:
            self.audio_player.seek(seconds)
        else:
            self.audio_player.play()
            self.audio_player.seek(seconds)
            self.btn_play.setText("⏸ (End)")
            self.is_playing = True
    
    def change_playback_speed(self, new_speed):
        """Change playback speed (only works with VLC)"""
        # Debug: see if we get here
        print(f"change_playback_speed called with {new_speed}, player: {self.audio_player}")

        if not self.audio_player:
            QMessageBox.information(self, "No Audio",
                "No audio file loaded.")
            return

        if not isinstance(self.audio_player, VlcAudioPlayer):
            QMessageBox.information(self, "Speed Control Not Available",
                "Playback speed control requires VLC media player.\n\n"
                "Please install VLC from https://www.videolan.org/vlc/")
            return

        new_speed = max(0.5, min(2.0, new_speed))

        # Don't process if speed hasn't changed
        if abs(new_speed - self.playback_speed) < 0.01:
            return

        self.playback_speed = new_speed
        self.audio_player.set_speed(new_speed)
    
    def on_playback_started(self):
        """Handle playback started"""
        self.is_playing = True
        logger.info("Playback started")
    
    def on_playback_paused(self):
        """Handle playback paused"""
        self.is_playing = False
        logger.info("Playback paused")
    
    def on_playback_stopped(self):
        """Handle playback stopped"""
        self.is_playing = False
        self.btn_play.setText("▶ (End)")
        logger.info("Playback stopped")
    
    def on_playback_ended(self):
        """Handle playback ended"""
        self.is_playing = False
        self.btn_play.setText("▶ (End)")
        logger.info("Playback ended")
    
    def on_position_changed(self, position):
        """Handle position change — updates waveform playback line."""
        if hasattr(self, 'waveform_viewer'):
            self.waveform_viewer.set_playback_position(position)

    # ── Waveform viewer callbacks ──────────────────────────────

    def _on_waveform_start_changed(self, seconds: float):
        """Update current block's start time from waveform drag."""
        if not self.srt_blocks or not (0 <= self.current_block_index < len(self.srt_blocks)):
            return
        self.push_undo()
        block = self.srt_blocks[self.current_block_index]
        block['start_time'] = self._seconds_to_srt(seconds)
        self.waveform_viewer.set_segment(seconds, self.waveform_viewer.end_time)
        self.update_display()
        self.mark_unsaved_changes()

    def _on_waveform_end_changed(self, seconds: float):
        """Update current block's end time from waveform drag."""
        if not self.srt_blocks or not (0 <= self.current_block_index < len(self.srt_blocks)):
            return
        self.push_undo()
        block = self.srt_blocks[self.current_block_index]
        block['end_time'] = self._seconds_to_srt(seconds)
        self.waveform_viewer.set_segment(self.waveform_viewer.start_time, seconds)
        self.update_display()
        self.mark_unsaved_changes()

    def _on_waveform_seek(self, seconds: float):
        """Seek audio to the clicked position in the waveform."""
        if self.audio_player:
            self.audio_player.seek(seconds)

    def _sync_waveform_with_current_block(self):
        """Sync waveform segment markers with the currently selected block."""
        if not hasattr(self, 'waveform_viewer'):
            return
        if not self.srt_blocks or not (0 <= self.current_block_index < len(self.srt_blocks)):
            self.waveform_viewer.clear_segment()
            return

        block = self.srt_blocks[self.current_block_index]
        start = block.get('start_time')
        end = block.get('end_time')

        from generators import time_to_seconds
        start_sec = time_to_seconds(start) if start else None
        end_sec = time_to_seconds(end) if end else None

        if start_sec is not None or end_sec is not None:
            self.waveform_viewer.set_segment(start_sec, end_sec)
        else:
            self.waveform_viewer.clear_segment()

    @staticmethod
    def _seconds_to_srt(seconds: float) -> str:
        """Convert seconds (float) to SRT time format HH:MM:SS,mmm."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        whole_secs = int(secs)
        ms = int((secs - whole_secs) * 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_secs:02d},{ms:03d}"

    def _load_waveform_audio(self, audio_path: str):
        """Load audio data into the waveform viewer."""
        if hasattr(self, 'waveform_viewer'):
            self.waveform_viewer.load_audio(audio_path)

    def _clear_waveform_audio(self):
        """Clear audio data from the waveform viewer (shows 'No audio loaded')."""
        if hasattr(self, 'waveform_viewer'):
            self.waveform_viewer.clear_audio()

    def auto_sync_with_audio(self, current_time):
        """Auto-sync transcript with audio position"""
        if not self.srt_blocks or not self.file_has_timestamps:
            return

        # Find block containing current time
        current_time_ms = current_time * 1000  # Convert to milliseconds
        buffer_ms = 100  # Small buffer for better sync

        # First check current block
        if 0 <= self.current_block_index < len(self.srt_blocks):
            block = self.srt_blocks[self.current_block_index]
            if block.get('start_time') and block.get('end_time'):
                start_ms = time_to_ms(block['start_time'])
                end_ms = time_to_ms(block['end_time'])

                if start_ms - buffer_ms <= current_time_ms <= end_ms + buffer_ms:
                    return  # Still in current block

        # Search for matching block
        for i, block in enumerate(self.srt_blocks):
            if block.get('start_time') and block.get('end_time'):
                start_ms = time_to_ms(block['start_time'])
                end_ms = time_to_ms(block['end_time'])

                if start_ms - buffer_ms <= current_time_ms <= end_ms + buffer_ms:
                    if i != self.current_block_index:
                        self.current_block_index = i
                        self.update_display()
                    break

    def time_to_ms(self, time_str):
        """Convert time string to milliseconds"""
        if not time_str:
            return 0
        
        if ',' in time_str:
            time_part, ms_part = time_str.split(',')
            ms = int(ms_part)
        else:
            time_part = time_str
            ms = 0
        
        parts = time_part.split(':')
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
        elif len(parts) == 2:
            hours = 0
            minutes = int(parts[0])
            seconds = int(parts[1])
        else:
            return 0
        
        return (hours * 3600 + minutes * 60 + seconds) * 1000 + ms
    
    def toggle_auto_sync(self, checked):
        """Toggle auto-sync"""
        self.auto_sync_enabled = checked
        logger.info(f"Auto-sync {'enabled' if checked else 'disabled'}")

    def toggle_auto_sync_shortcut(self):
        if self.auto_sync_check.isEnabled():
            self.auto_sync_check.toggle()
    
    def toggle_auto_pause(self, checked):
        """Toggle auto-pause"""
        self.auto_pause_enabled = checked
        logger.info(f"Auto-pause {'enabled' if checked else 'disabled'}")
              



    
    def new_project(self):
        """Create new project"""
        self.undo_stack.clear()
        self.redo_stack.clear()
        if self.check_unsaved_changes():
            self.srt_blocks = []
            self.current_block_index = 0
            self.current_file_path = None
            self.project_name = ""
            self.project_memo = ""
            self.has_unsaved_changes = False
            
            self.speakers = ["A", "B", "C", "D"]
            self.speaker_count_label.setText("4")
            
            # Stop audio
            if self.audio_player:
                self.audio_player.cleanup()
                self.audio_player = None
            
            self.audio_file_path = None
            self._clear_waveform_audio()
            self.audio_info_label.setText("No audio loaded")
            self.btn_play.setEnabled(False)
            self.btn_rewind.setEnabled(False)
            self.btn_forward.setEnabled(False)
            self.auto_sync_check.setEnabled(False)
            self.auto_pause_check.setEnabled(False)
            self.auto_sync_check.setChecked(False)
            self.auto_pause_check.setChecked(False)
            self.audio_progress.setEnabled(False)
            self.time_label.setText("00:00 / 00:00")
            self.audio_progress.setValue(0)
            
            # Reset speed to 1.0
            self.playback_speed = 1.0
            self.speed_knob.value = 1.0
            self.speed_knob.update()
            
            self.clear_search_highlights()
            self.unassigned_list.clear()
            self.unassigned_blocks_label.setText("Unassigned Segments (0/0):")
            self.create_speaker_widgets()
            self.setup_shortcuts()
            
            self.update_display()
            self.clear_unsaved_changes()
            self.update_menu_state()
            
    def check_unsaved_changes(self):
        """Check if there are unsaved changes and prompt to save"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, 
                "Unsaved Changes", 
                "You have unsaved changes. Would you like to save them?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Save:
                # Use Save As to ensure we're saving as a project file, not overwriting the original transcript
                return self.save_project(force_save_as=True)
            elif reply == QMessageBox.Discard:
                return True
            else:  # Cancel
                return False
        return True

    def open_search_dialog(self):
        """Open the search dialog"""
        if not hasattr(self, 'search_dialog') or not self.search_dialog:
            self.search_dialog = SearchDialog(self)
            self.search_dialog.show()
        else:
            self.search_dialog.show()
            self.search_dialog.activateWindow()
            self.search_dialog.search_input.setFocus()
            
    def highlight_search_match(self, block_idx, start_pos, end_pos):
        """Highlight a specific search match and navigate to it"""
        # Navigate to the block
        self.current_block_index = block_idx
        self.update_display()
        
        # Highlight the text within the block
        cursor = self.text_display.textCursor()
        cursor.select(cursor.Document)
        
        # Clear previous extra selections
        self.text_display.setExtraSelections([])
        
        start_idx = max(0, self.current_block_index - self.context_blocks)
        display_block_pos = max(0, (block_idx - start_idx) * 2)
        doc_block = self.text_display.document().findBlockByNumber(display_block_pos)
        if not doc_block.isValid():
            return

        # Anchor the selection to the target paragraph, then offset into block text.
        # This remains stable regardless of soft wrapping width.
        prefix_len = min(3, len(doc_block.text()))
        text_len = max(0, len(doc_block.text()) - prefix_len)
        clamped_start = max(0, min(start_pos, text_len))
        clamped_end = max(clamped_start, min(end_pos, text_len))

        cursor = QTextCursor(doc_block)
        anchor_pos = doc_block.position() + prefix_len
        cursor.setPosition(anchor_pos + clamped_start)
        cursor.setPosition(anchor_pos + clamped_end, QTextCursor.KeepAnchor)
        
        # Create and apply highlight
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(QColor(255, 255, 0))
        selection.format.setForeground(QColor(0, 0, 0))
        
        self.text_display.setExtraSelections([selection])
        self.text_display.setTextCursor(cursor)
        self.text_display.ensureCursorVisible()
        
    def clear_search_highlights(self):
        """Clear all search highlights"""
        self.text_display.setExtraSelections([])


    def show_shortcuts(self):
        """Show keyboard shortcuts dialog"""
        shortcuts_text = """
Keyboard Shortcuts:

Navigation:
• P / Left Arrow: Previous block
• N / Right Arrow: Next block

Assigning Speakers:
• 1-4: Assign speakers A-D
• U: Unassign current block

Editing:
• Space: Split current block
• Delete: Merge with next block
• E/F2: Edit segment content
• T: Edit segment timestamp
• Enter: Insert empty line
• Ctrl+Del: Remove overlap

Transcription Symbols:
• *: Open symbols dialog
• .: Insert micropause (with placement)
• h: Insert short inhale (with placement)
• H: Insert short exhale (with placement)

Audio Controls:
• End: Play/Pause audio
• PgUp: Rewind 5 seconds
• PgDn: Fast forward 5 seconds
• Ctrl+J: Jump to Time
• Shift+L: Jump to Current Audio Location
• Ctrl+L: Toggle Auto-sync to Audio
• Shift+Enter: Play from current segment
• -: Lower Playback Speed
• +: Speed up Playback

Search Functions:
• Ctrl+F: Open Search Dialog
• F3: Find Next
• Shift+F3: Find Previous

File Operations:
• Ctrl+N: New Project
• Ctrl+O: Open Project
• Ctrl+S: Save Project
• Ctrl+Return: Export Transcript

Help:
• F1: Show Shortcuts (this dialog)
• Ctrl+F1: Open Online Manual (requires internet)
"""
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)
        
    def open_manual(self):
        """Open online manual in browser"""
        webbrowser.open("https://github.com/anouarg88/CapsQual/wiki")
        
    def show_about(self):
        """Show about dialog"""
        about_text = """
<b style="font-size: 16px;">CapsQual 1.6.1</b><br><br>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
<br><br>
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
<br><br>
You should have received a copy of the GNU General Public License along with this program.  If not, see 
<a href="https://www.gnu.org/licenses/">https://www.gnu.org/licenses/</a>.
<br><br>
(c) 2026 Anouâr Gadermann
<br>
CapsQual was engineered with the help of DeepSeek AI.

"""
        QMessageBox.about(self, "About CapsQual", about_text)
        
    def mark_unsaved_changes(self):
        """Mark that there are unsaved changes"""
        self.has_unsaved_changes = True
        base_title = "CapsQual 1.6.1 - Subtitle-to-Transcript Workstation"
        if self.project_name:
            self.setWindowTitle(f"{base_title} - {self.project_name} *")
        else:
            self.setWindowTitle(f"{base_title} *")
            
    def clear_unsaved_changes(self):
        """Clear unsaved changes marker"""
        self.has_unsaved_changes = False
        base_title = "CapsQual 1.6.1 - Subtitle-to-Transcript Workstation"
        if self.project_name:
            self.setWindowTitle(f"{base_title} - {self.project_name}")
        else:
            self.setWindowTitle(base_title)
            
    def find_next(self):
        """Find next occurrence (for F3 shortcut)"""
        if hasattr(self, 'search_dialog') and self.search_dialog and self.search_dialog.isVisible():
            self.search_dialog.next_match()
            
    def find_previous(self):
        """Find previous occurrence (for Shift+F3 shortcut)"""
        if hasattr(self, 'search_dialog') and self.search_dialog and self.search_dialog.isVisible():
            self.search_dialog.previous_match()
        
    def import_subtitles(self):
        """Import subtitles via menu"""
        self.load_file()
        
    def save_project_as(self):
        """Save project with new filename"""
        self.save_project(force_save_as=True)
        
    def _base_dir_for_dialog(self):
        """Return the user-configured base directory, or '' for system default."""
        base = QSettings('CapsQual', 'Preferences').value('base_directory', '')
        if base and Path(base).is_dir():
            return base
        return ''

    def open_settings(self):
        old_font = QFont(self.text_display_font)
        old_cjk = self.cjk_mode
        old_base = QSettings('CapsQual', 'Preferences').value('base_directory', '')
        dialog = SettingsDialog(self.text_display_font, self.current_theme, self.cjk_mode,
                                old_base, self)
        if dialog.exec_() == QDialog.Accepted:
            new_font = dialog.get_font()
            new_cjk = dialog.get_cjk_mode()
            theme = dialog.get_theme()
            new_base = dialog.get_base_directory()

            # Apply theme globally (persisted via QSettings — not a project change)
            self.apply_viewer_theme(theme)

            # Apply base directory globally
            if new_base != old_base:
                QSettings('CapsQual', 'Preferences').setValue('base_directory', new_base)

            # Apply font and CJK mode
            font_changed = (new_font.family() != old_font.family() or
                            new_font.pointSize() != old_font.pointSize())
            if font_changed:
                self.text_display_font = new_font
                self.text_display.setFont(self.text_display_font)
            if new_cjk != old_cjk:
                self.cjk_mode = new_cjk
                self.update_display()   # refresh display to apply indentation changes

            # Only mark unsaved if font or CJK mode changed (theme is global, not project-scoped)
            if font_changed or new_cjk != old_cjk:
                self.mark_unsaved_changes()
            
    def open_project_memo(self):
        """Open project memo dialog"""
        dialog = ProjectMemoDialog(self.project_name, self.project_memo, self)
        if dialog.exec_() == QDialog.Accepted:
            project_info = dialog.get_project_info()
            self.project_name = project_info['name']
            self.project_memo = project_info['memo']
            self.mark_unsaved_changes()
            self.clear_unsaved_changes()
        
    def ms_to_time(self, ms):
        """Convert milliseconds to SRT time format"""
        hours = int(ms // 3600000)
        ms %= 3600000
        minutes = int(ms // 60000)
        ms %= 60000
        seconds = int(ms // 1000)
        milliseconds = int(ms % 1000)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
     
    def load_file(self):
        if not self.check_unsaved_changes():
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", self._base_dir_for_dialog(), 
            "All Supported Files (*.srt *.vtt *.txt *.json *.tsv);;SRT Files (*.srt);;VTT Files (*.vtt);;Text Files (*.txt);;JSON Files (*.json);;TSV Files (*.tsv)"
        )
        if file_path:
            self.load_file_from_path(file_path)

    def load_file_from_path(self, file_path):
        """Load a subtitle file from given path."""
        print(f"load_file_from_path called with: {file_path}")  # DEBUG
        try:
            file_extension = Path(file_path).suffix.lower()

            if file_extension == '.srt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.transcript.blocks = parse_srt(content)
                self.update_menu_state()
                self.file_has_timestamps = True


            elif file_extension == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.transcript.blocks = parse_text(content)
                self.update_menu_state()
                self.file_has_timestamps = False

            elif file_extension == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                self.transcript.blocks = parse_json(content)
                self.update_menu_state()
                self.file_has_timestamps = any(block.get('start_time')
                                               for block in self.transcript.blocks)

            elif file_extension == '.tsv':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.transcript.blocks = parse_tsv(content)
                self.update_menu_state()
                self.file_has_timestamps = True

            elif file_extension == '.vtt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.transcript.blocks = parse_vtt(content)
                self.update_menu_state()
                self.file_has_timestamps = True

            self.current_block_index = 0
            self.current_file_path = file_path

            # Only enable auto-sync checkbox and play from segment button if we have timestamps AND audio is loaded
            self.auto_sync_check.setEnabled(self.file_has_timestamps and self.audio_file_path is not None)
            self.btn_play_segment.setEnabled(self.audio_file_path is not None and self.file_has_timestamps)
            # Auto-pause is always enabled when audio is loaded
            self.auto_pause_check.setEnabled(self.audio_file_path is not None)

            # Ensure checkboxes reflect the actual state
            self.auto_sync_check.setChecked(self.auto_sync_enabled)
            self.auto_pause_check.setChecked(self.auto_pause_enabled)

            self.add_to_recent(file_path)

            self.update_display()
            self.mark_unsaved_changes()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update_undo_redo_actions()

            # Clear search highlights
            self.clear_search_highlights()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load file: {str(e)}")
            logger.error(f"Failed to load file {file_path}: {e}")

    def load_project(self):
        if not self.check_unsaved_changes():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", self._base_dir_for_dialog(),
            "CapsQual/CapsGAT Project (*.capsqual *.capsgat);;All Files (*)"
        )
        if file_path:
            self.load_project_from_path(file_path)

    def load_project_from_path(self, file_path):
        """Load a CapsQual project file from the given path."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f)

            self.transcript.blocks = project_data['srt_blocks']
            for block in self.transcript.blocks:
                if 'raw_text' not in block:
                    block['raw_text'] = block['text']
                if 'overlap' in block:
                    del block['overlap']
                if block.get('overlap_info') and block.get('is_empty'):
                    del block['is_empty']
            # Check for old-format overlap blocks (␣ placeholders without overlap_info)
            # and ask user to upgrade if found
            self._check_and_upgrade_old_overlap_format()

            self.current_block_index = project_data['current_block_index']
            self.transcript.speakers = project_data['speakers']
            # Use the actual project file path being opened, not the stored source_file
            self.current_file_path = file_path
            # Preserve original source file path separately for reference
            self.source_file = project_data.get('source_file', '')
            self.file_has_timestamps = project_data.get('file_has_timestamps', True)
            self.project_name = project_data.get('project_name', '')
            self.project_memo = project_data.get('project_memo', '')
            self.playback_speed = project_data.get('playback_speed', 1.0)
            self.cjk_mode = project_data.get('cjk_mode', False)
            self.timestamp_style = project_data.get('timestamp_style', 'curly')
            self.custom_timestamp_pattern = project_data.get('custom_timestamp_pattern', '{HH:mm:ss}')

            font_data = project_data.get('text_display_font')
            if font_data:
                self.text_display_font = QFont(font_data['family'], font_data['size'])
                self.text_display.setFont(self.text_display_font)

            audio_path = project_data.get('audio_file_path')
            if audio_path and Path(audio_path).exists():
                self.audio_file_path = audio_path
                self.original_audio_duration = 0
                self.load_audio_file_for_project(audio_path, self.playback_speed)

            # Theme is no longer project-scoped — ignore viewer_theme from old
            # project files. Theme preference is managed via QSettings globally.

            self.speed_knob.value = self.playback_speed
            self.speed_knob.update()

            self.add_to_recent(file_path)
            self.update_display()
            self.update_menu_state()
            self.clear_unsaved_changes()

            QMessageBox.information(self, "Success", f"Project loaded from {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load project: {str(e)}")


    def create_speaker_widgets(self):
        for i in reversed(range(self.speaker_layout.count())): 
            self.speaker_layout.itemAt(i).widget().setParent(None)
        
        self.speaker_layout.setSpacing(3)
        self.speaker_layout.setContentsMargins(0, 0, 0, 0)
        
        self.speaker_widgets = []
        for i, speaker in enumerate(self.speakers):
            speaker_widget = QWidget()
            speaker_layout = QHBoxLayout(speaker_widget)
            speaker_layout.setSpacing(3)
            speaker_layout.setContentsMargins(5, 2, 5, 2)
            
            color_label = QLabel("■")
            color_label.setStyleSheet(f"color: {self.speaker_colors[i].name()}; font-size: 20px;")
            
            speaker_name_edit = QLineEdit(speaker)
            speaker_name_edit.editingFinished.connect(lambda checked=False, idx=i: self.rename_speaker(idx))
            speaker_name_edit.setFixedWidth(120)
            speaker_name_edit.setMinimumHeight(18)
            speaker_name_edit.setStyleSheet("""
                QLineEdit {
                    background-color: palette(base);
                    color: palette(text);
                    border: 2px solid palette(mid);
                    border-radius: 3px;
                    padding: 2px;
                }
            """)
            
            speaker_btn = QPushButton(f"Assign ({i+1})")
            speaker_btn.clicked.connect(lambda checked, idx=i: self.assign_speaker(idx))
            speaker_btn.setMinimumHeight(18)
            
            if self.current_theme == "dark":
                speaker_btn.setStyleSheet(f"""
                    QPushButton {{ 
                        background-color: {self.speaker_colors[i].name()}; 
                        color: white;
                        border: 2px solid palette(mid);
                        padding: 1px 1px;
                        font-weight: bold;
                        min-width: 100px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.speaker_colors[i].lighter(120).name()};
                        color: white;
                    }}
                """)
            else:
                speaker_btn.setStyleSheet(f"""
                    QPushButton {{ 
                        background-color: {self.speaker_colors[i].name()}; 
                        border: 2px solid palette(mid);
                        padding: 1px 1px;
                        font-weight: bold;
                        min-width: 100px;
                    }}
                    QPushButton:hover {{
                        background-color: {self.speaker_colors[i].lighter(120).name()};
                    }}
                """)
            
            speaker_layout.addWidget(color_label)
            speaker_layout.addWidget(QLabel("Name:"))
            speaker_layout.addWidget(speaker_name_edit)
            speaker_layout.addStretch(1)
            speaker_layout.addWidget(speaker_btn)
            
            centered_widget = QWidget()
            centered_widget.setMinimumHeight(20)
            centered_layout = QHBoxLayout(centered_widget)
            centered_layout.setSpacing(0)
            centered_layout.setContentsMargins(0, 0, 0, 0)
            centered_layout.addStretch(1)
            centered_layout.addWidget(speaker_widget)
            centered_layout.addStretch(1)
            
            self.speaker_layout.addWidget(centered_widget)
            self.speaker_widgets.append({
                'name_edit': speaker_name_edit,
                'button': speaker_btn
            })

    def rename_speaker(self, speaker_idx):
        new_name = self.speaker_widgets[speaker_idx]['name_edit'].text()
        if speaker_idx < len(self.speakers) and self.speakers[speaker_idx] != new_name:
            self.push_undo()
            self.speakers[speaker_idx] = new_name
            self.update_display()
            self.mark_unsaved_changes()

    def count_blocks_for_speaker(self, speaker_idx):
        """Count how many blocks are assigned to a specific speaker"""
        count = 0
        for block in self.srt_blocks:
            if block.get('speaker') == speaker_idx:
                count += 1
        return count

    def update_speaker_count(self, count):
        while len(self.speakers) > count:
            self.speakers.pop()
        
        while len(self.speakers) < count:
            new_idx = len(self.speakers)
            self.speakers.append(chr(65 + new_idx))
        
        self.speaker_colors = []
        for i in range(len(self.speakers)):
            if i < len(self.speaker_color_palette):
                self.speaker_colors.append(self.speaker_color_palette[i])
            else:
                self.speaker_colors.append(QColor(200, 200, 200))
        
        self.create_speaker_widgets()
        self.setup_shortcuts()
        self.update_display()
        self.mark_unsaved_changes()
        
        self.speaker_count_label.setText(str(count))
        self.update_speaker_buttons()

    def load_audio_file_for_project(self, audio_path, speed):
        """Load audio file for a project (without showing file dialog)"""
        # Stop any existing audio
        if self.audio_player:
            self.audio_player.cleanup()
            self.audio_player = None

        # Try to create VLC player first
        try:
            self.audio_player = VlcAudioPlayer()
            vlc_ok = True
        except Exception:
            # Fallback to simple player
            if has_pyaudio():
                self.audio_player = SimpleAudioPlayer()
                vlc_ok = False
            else:
                logger.error("No audio backend available for project loading")
                return

        # Connect signals
        self.audio_player.playback_started.connect(self.on_playback_started)
        self.audio_player.playback_stopped.connect(self.on_playback_stopped)
        self.audio_player.position_changed.connect(self.on_position_changed)

        try:
            # Load audio file
            if not self.audio_player.load_file(audio_path):
                raise Exception("Failed to load audio file")

            # Get duration from the loaded player
            self.original_audio_duration = self.audio_player.duration
            self.audio_file_path = audio_path
            # Load waveform for visual display
            self._load_waveform_audio(audio_path)
            self.playback_speed = 1.0
            self.speed_knob.value = 1.0
            self.speed_knob.update()

            # Update UI
            audio_name = Path(audio_path).name
            self.audio_info_label.setText(f"Audio: {audio_name}")

            # Enable controls
            self.btn_play.setEnabled(True)
            self.btn_rewind.setEnabled(True)
            self.btn_forward.setEnabled(True)
            self.btn_play_segment.setEnabled(True)
            self.auto_sync_check.setEnabled(self.file_has_timestamps)
            self.auto_pause_check.setEnabled(True)
            self.audio_progress.setEnabled(True)

            self.update_speed_controls_state()

            logger.info(f"Audio loaded for project at normal speed: {audio_name}")

        except Exception as e:
            logger.error(f"Failed to load audio for project: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load audio: {str(e)}")
            self.audio_player = None
            self._clear_waveform_audio()
    @staticmethod
    def _light_palette():
        """QPalette for the light theme."""
        p = QPalette()
        p.setColor(QPalette.Window, QColor(240, 240, 240))
        p.setColor(QPalette.WindowText, QColor(30, 30, 30))
        p.setColor(QPalette.Base, QColor(255, 255, 255))
        p.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        p.setColor(QPalette.Text, QColor(30, 30, 30))
        p.setColor(QPalette.Button, QColor(255, 255, 255))
        p.setColor(QPalette.ButtonText, QColor(30, 30, 30))
        p.setColor(QPalette.Highlight, QColor(100, 123, 234))
        p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        p.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
        p.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
        p.setColor(QPalette.Mid, QColor(200, 200, 200))
        p.setColor(QPalette.Dark, QColor(180, 180, 180))
        p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(160, 160, 160))
        p.setColor(QPalette.Disabled, QPalette.Text, QColor(160, 160, 160))
        p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(160, 160, 160))
        return p

    @staticmethod
    def _dark_palette():
        """QPalette for the dark theme."""
        p = QPalette()
        p.setColor(QPalette.Window, QColor(45, 45, 48))
        p.setColor(QPalette.WindowText, QColor(200, 200, 200))
        p.setColor(QPalette.Base, QColor(21, 21, 25))
        p.setColor(QPalette.AlternateBase, QColor(55, 55, 58))
        p.setColor(QPalette.Text, QColor(204, 204, 204))
        p.setColor(QPalette.Button, QColor(58, 58, 58))
        p.setColor(QPalette.ButtonText, QColor(200, 200, 200))
        p.setColor(QPalette.Highlight, QColor(100, 123, 234))
        p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        p.setColor(QPalette.ToolTipBase, QColor(60, 60, 65))
        p.setColor(QPalette.ToolTipText, QColor(200, 200, 200))
        p.setColor(QPalette.Mid, QColor(85, 85, 85))
        p.setColor(QPalette.Dark, QColor(50, 50, 50))
        p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(120, 120, 120))
        p.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
        p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
        return p

    def _apply_theme_qss(self):
        """(Re)apply global stylesheet using palette() references.

        Set on QApplication so that *all* windows (including dialogs)
        inherit the same QSS rules.  Widget types such as QPushButton,
        QScrollBar, QCheckBox, QRadioButton, QComboBox, QSpinBox, QSlider,
        QMenuBar, QToolButton, and QGroupBox ignore QPalette on Windows
        and require QSS.
        """
        app = QApplication.instance()
        pal = app.palette()
        # Inject concrete hex colours for sub-controls where palette() is
        # unreliable (notably QGroupBox::title).
        _wt = pal.color(QPalette.WindowText).name()
        _tex = pal.color(QPalette.Text).name()
        _btn = pal.color(QPalette.Button).name()
        _btnt = pal.color(QPalette.ButtonText).name()
        _base = pal.color(QPalette.Base).name()
        _win = pal.color(QPalette.Window).name()
        _mid = pal.color(QPalette.Mid).name()
        _dark = pal.color(QPalette.Dark).name()
        _light = pal.color(QPalette.Light).name()
        _hl = pal.color(QPalette.Highlight).name()
        _hlt = pal.color(QPalette.HighlightedText).name()
        _dis_btnt = pal.color(QPalette.Disabled, QPalette.ButtonText).name()
        # Compute button hover colours per theme
        if self.current_theme == "dark":
            _btn_hover = QColor(70, 70, 73).name()  # slightly brighter than button(58)
            _btnt_hover = pal.color(QPalette.ButtonText).name()  # same text colour
        else:
            _btn_hover = _hl  # use highlight blue in light mode
            _btnt_hover = _hlt  # white text on blue

        app.setStyleSheet(f"""
            /* ── Menu bar ─────────────────────────────────────── */
            QMenuBar {{
                background-color: {_win};
                color: {_wt};
                border-bottom: 1px solid {_mid};
            }}
            QMenuBar::item {{
                background: transparent;
                color: {_wt};
                padding: 4px 10px;
            }}
            QMenuBar::item:selected {{
                background-color: {_hl};
                color: {_hlt};
            }}
            QMenu {{
                background-color: {_win};
                color: {_wt};
                border: 1px solid {_mid};
            }}
            QMenu::item {{
                padding: 4px 20px;
                color: {_wt};
            }}
            QMenu::item:selected {{
                background-color: {_hl};
                color: {_hlt};
            }}
            QMenu::separator {{
                height: 1px;
                background: {_mid};
                margin: 4px 8px;
            }}

            /* ── Push buttons ─────────────────────────────────── */
            QPushButton {{
                background-color: {_btn};
                color: {_btnt};
                border: 1px solid {_mid};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {_btn_hover};
                color: {_btnt_hover};
                border-color: {_dark};
            }}
            QPushButton:pressed {{
                background-color: {_mid};
            }}
            QPushButton:disabled {{
                background-color: {_win};
                color: {_dis_btnt};
                border-color: {_mid};
            }}

            /* ── Message boxes ────────────────────────────────── */
            QMessageBox {{
                background-color: {_win};
                color: {_wt};
            }}
            QMessageBox QLabel {{
                color: {_wt};
            }}
            QMessageBox QPushButton {{
                min-width: 70px;
            }}

            /* ── Tool buttons (splitter toggle, etc.) ─────────── */
            QToolButton {{
                background-color: {_btn};
                color: {_btnt};
                border: 1px solid {_mid};
                border-radius: 4px;
            }}
            QToolButton:hover {{
                background-color: {_btn_hover};
                color: {_btnt_hover};
                border-color: {_dark};
            }}
            QToolButton:disabled {{
                background-color: {_win};
                color: {_dis_btnt};
                border-color: {_mid};
            }}

            /* ── Group boxes ──────────────────────────────────── */
            QGroupBox {{
                border: 1px solid {_mid};
                border-radius: 3px;
                margin-top: 0.9em;
                font-size: 11px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: {_wt};
            }}

            /* ── Scroll bars ──────────────────────────────────── */
            QScrollBar:vertical {{
                background: {_win};
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_mid};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_dark};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                background: {_win};
                height: 10px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {_mid};
                min-width: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {_dark};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            /* ── List widget ──────────────────────────────────── */
            QListWidget {{
                background-color: {_base};
                color: {_tex};
                border: 1px solid {_mid};
                border-radius: 4px;
                padding: 2px;
            }}
            QListWidget::item {{
                color: {_tex};
            }}
            QListWidget:disabled {{
                background-color: {_win};
                color: {_dis_btnt};
                border-color: {_mid};
            }}

            /* ── Check boxes / radio buttons ──────────────────── */
            QCheckBox, QRadioButton {{
                color: {_wt};
                spacing: 4px;
            }}
            QCheckBox:disabled, QRadioButton:disabled {{
                color: {_dis_btnt};
            }}
            QCheckBox::indicator, QRadioButton::indicator {{
                width: 14px;
                height: 14px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {_hl};
                border: 1px solid {_hl};
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {_base};
                border: 1px solid {_mid};
            }}
            QCheckBox::indicator:hover:unchecked {{
                border-color: {_hl};
            }}
            QCheckBox::indicator:disabled:checked {{
                background-color: {_mid};
                border: 1px solid {_mid};
            }}
            QCheckBox::indicator:disabled:unchecked {{
                background-color: {_win};
                border: 1px solid {_mid};
            }}
            QRadioButton::indicator:checked {{
                background: qradialgradient(
                    cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                    stop:0 #ffffff, stop:0.40 #ffffff,
                    stop:0.42 {_hl}, stop:1 {_hl}
                );
                border: 1px solid {_hl};
                border-radius: 7px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {_base};
                border: 1px solid {_mid};
                border-radius: 7px;
            }}
            QRadioButton::indicator:hover:unchecked {{
                border-color: {_hl};
            }}

            /* ── Combo box (dropdown) ─────────────────────────── */
            QComboBox {{
                background-color: {_base};
                color: {_tex};
                border: 1px solid {_mid};
                border-radius: 4px;
                padding: 2px 6px;
            }}
            QComboBox:hover {{
                border-color: {_dark};
            }}
            QComboBox:disabled {{
                background-color: {_win};
                color: {_dis_btnt};
                border-color: {_mid};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid {_mid};
            }}
            QComboBox QAbstractItemView {{
                background-color: {_win};
                color: {_wt};
                selection-background-color: {_hl};
                selection-color: {_hlt};
            }}

            /* ── Spin boxes ───────────────────────────────────── */
            QSpinBox, QDoubleSpinBox {{
                background-color: {_base};
                color: {_tex};
                border: 1px solid {_mid};
                border-radius: 4px;
                padding: 2px 4px;
            }}
            QSpinBox:disabled, QDoubleSpinBox:disabled {{
                background-color: {_win};
                color: {_dis_btnt};
                border-color: {_mid};
            }}

            /* ── Text input fields ────────────────────────────── */
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background-color: {_base};
                color: {_tex};
                border: 1px solid {_mid};
                border-radius: 4px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {_hl};
            }}
            QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
                background-color: {_win};
                color: {_dis_btnt};
                border-color: {_mid};
            }}

            /* ── Slider (audio progress) ──────────────────────── */
            QSlider::groove:horizontal {{
                background: {_mid};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {_hl};
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_hl};
                border-radius: 3px;
            }}
            QSlider::add-page:horizontal {{
                background: {_mid};
                border-radius: 3px;
            }}

            /* ── Labels ───────────────────────────────────────── */
            QLabel {{
                color: {_wt};
            }}
            QLabel:disabled {{
                color: {_dis_btnt};
            }}
        """)
        # ── Per-widget overrides (different border-radius/padding) ──
        self.text_display.setStyleSheet("""
            QTextEdit {
                background-color: palette(base);
                color: palette(text);
                border: 2px solid palette(mid);
                border-radius: 5px;
                padding: 10px;
            }
        """)
        self.current_info_label.setStyleSheet("""
            QLabel {
                background-color: palette(window);
                color: palette(windowtext);
                padding: 10px;
                border: 2px solid palette(mid);
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        self.audio_info_label.setStyleSheet("""
            QLabel {
                padding: 0px;
                border-radius: 3px;
                font-size: 11px;
            }
        """)

    def apply_viewer_theme(self, theme):
        self.current_theme = theme

        # Persist theme to global QSettings (NOT per-project)
        QSettings('CapsQual', 'Preferences').setValue('viewer_theme', theme)

        # 1. Set global palette on QApplication — affects every widget
        app = QApplication.instance()
        app.setPalette(self._dark_palette() if theme == "dark" else self._light_palette())

        # 2. Re-apply structural QSS so palette() references re-evaluate
        self._apply_theme_qss()

        # 3. Update speaker colour palette
        if theme == "dark":
            self.speaker_color_palette = [
                QColor(80, 120, 160),   # Steel blue
                QColor(170, 80, 80),    # Brick red
                QColor(75, 155, 75),    # Forest green
                QColor(170, 170, 80),   # Olive yellow
                QColor(130, 80, 170),   # Amethyst
                QColor(175, 110, 60),   # Burnt orange
                QColor(65, 130, 130),   # Teal
                QColor(170, 80, 120)    # Rose
            ]
        else:
            self.speaker_color_palette = [
                QColor(220, 240, 255),  # Light blue
                QColor(255, 220, 220),  # Light red
                QColor(220, 255, 220),  # Light green
                QColor(255, 255, 200),  # Light yellow
                QColor(230, 200, 255),  # Light purple
                QColor(255, 200, 150),  # Light orange
                QColor(200, 230, 230),  # Light cyan
                QColor(255, 210, 230)   # Light pink
            ]

        # 4. Rebuild speaker colors from new palette
        self.speaker_colors = []
        for i in range(len(self.speakers)):
            if i < len(self.speaker_color_palette):
                self.speaker_colors.append(self.speaker_color_palette[i])
            else:
                self.speaker_colors.append(QColor(200, 200, 200))

        # 5. Sync waveform viewer theme
        if hasattr(self, 'waveform_viewer'):
            self.waveform_viewer.set_theme(theme)
        # 6. Update export button style for current theme
        if theme == "dark":
            self.btn_quick_export.setStyleSheet("""
                QPushButton {
                    background-color: #1e7230;
                    padding: 2px 7px;
                    font-size: 12px;
                    font-weight: bold;
                    color: white;
                    border: 0px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #2d9e45;
                }
            """)
        else:
            self.btn_quick_export.setStyleSheet("""
                QPushButton {
                    background-color: #124607;
                    padding: 2px 7px;
                    font-size: 12px;
                    font-weight: bold;
                    color: white;
                    border: 0px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #71906a;
                }
            """)

        self.create_speaker_widgets()
        self.update_display()
    
    
    def update_display(self):
        if not self.srt_blocks:
            self.text_display.setPlainText("No content loaded")
            self.current_info_label.setText("No block selected")
            self.lbl_current.setText("Current: -/-")
            # Update unassigned counter
            self.unassigned_blocks_label.setText("Unassigned Segments (0/0):")
            return
        
        current_block = self.srt_blocks[self.current_block_index]
        speaker_name = self.speakers[current_block['speaker']] if current_block['speaker'] is not None else "UNASSIGNED"
        turn_indicator = " [TURN START]" if current_block.get('is_turn_start', True) else " [CONTINUATION]"
        self.current_info_label.setText(
            f"{current_block['index']} | {speaker_name}{turn_indicator} | "
            f"{current_block['start_time']} --> {current_block['end_time']}"
        )
        
        start_idx = max(0, self.current_block_index - self.context_blocks)
        end_idx = min(len(self.srt_blocks), self.current_block_index + self.context_blocks + 1)
        
        display_text = ""
        for i in range(start_idx, end_idx):
            block = self.srt_blocks[i]
            # Use raw_text directly (contains placeholders)
            display_text_block = block['raw_text']
            if i == self.current_block_index:
                display_text += f">> {display_text_block}\n\n"
            else:
                display_text += f"   {display_text_block}\n\n"
        
        self.text_display.setPlainText(display_text)
        
        self.colorize_display()
        
        self.lbl_current.setText(f"Current: {self.current_block_index + 1}/{len(self.srt_blocks)}")
        
        # Update unassigned list with counter
        self.unassigned_list.clear()
        unassigned_count = 0
        total_blocks = len(self.srt_blocks)
        
        for i, block in enumerate(self.srt_blocks):
            if block['speaker'] is None:
                unassigned_count += 1
                preview = block['text'][:50] + "..." if len(block['text']) > 50 else block['text']
                self.unassigned_list.addItem(f"{i+1}: {preview}")
        
        # Update label with counter
        self.unassigned_blocks_label.setText(f"Unassigned Segments ({unassigned_count}/{total_blocks}):")

        # Sync waveform viewer with the current block
        self._sync_waveform_with_current_block()

    def _display_block_paragraph(self, block_idx, start_idx):
        """Return the QTextDocument paragraph index for a segment in transcript display."""
        return max(0, (block_idx - start_idx) * 2)

    def _segment_cursor_for_display_block(self, block_idx, start_idx):
        """Return a cursor selecting the segment paragraph (without spacer line)."""
        paragraph_idx = self._display_block_paragraph(block_idx, start_idx)
        doc_block = self.text_display.document().findBlockByNumber(paragraph_idx)
        if not doc_block.isValid():
            return None

        cursor = QTextCursor(doc_block)
        cursor.setPosition(doc_block.position())
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        return cursor
    
    def colorize_display(self):
        cursor = self.text_display.textCursor()
        cursor.select(QTextCursor.Document)
        
        format_normal = QTextCharFormat()
        cursor.setCharFormat(format_normal)
        
        start_idx = max(0, self.current_block_index - self.context_blocks)
        
        for i in range(start_idx, min(len(self.srt_blocks), self.current_block_index + self.context_blocks + 1)):
            block = self.srt_blocks[i]
            if block['speaker'] is not None and block['speaker'] < len(self.speaker_colors):
                color = self.speaker_colors[block['speaker']]

                segment_cursor = self._segment_cursor_for_display_block(i, start_idx)
                if segment_cursor is None:
                    continue

                block_format = QTextCharFormat()
                block_format.setBackground(color)
                segment_cursor.setCharFormat(block_format)

        current_cursor = self._segment_cursor_for_display_block(self.current_block_index, start_idx)
        if current_cursor is None:
            return

        current_format = QTextCharFormat()
        if self.current_theme == "dark":
            current_format.setBackground(QColor(80, 80, 160))
        else:
            current_format.setBackground(QColor(255, 240, 200))
        current_format.setFontWeight(QFont.Bold)
        current_cursor.setCharFormat(current_format)
        
        self.scroll_to_current_block()
    
    def scroll_to_current_block(self):
        start_idx = max(0, self.current_block_index - self.context_blocks)
        paragraph_idx = self._display_block_paragraph(self.current_block_index, start_idx)
        doc_block = self.text_display.document().findBlockByNumber(paragraph_idx)
        if not doc_block.isValid():
            return

        cursor = QTextCursor(doc_block)
        cursor.setPosition(doc_block.position())
        self.text_display.setTextCursor(cursor)
        self.text_display.ensureCursorVisible()
        
    def previous_block(self):
        if self.current_block_index > 0:
            self.current_block_index -= 1
            self.update_display()
            
    def next_block(self):
        if self.current_block_index < len(self.srt_blocks) - 1:
            self.current_block_index += 1
            self.update_display()
            
    def assign_speaker(self, speaker_idx):
        if not self.srt_blocks or speaker_idx >= len(self.speakers):
            return
        self.push_undo()
            
        current_block = self.srt_blocks[self.current_block_index]
        current_block['speaker'] = speaker_idx
        
        is_turn_start = True
        if self.current_block_index > 0:
            prev_block = self.srt_blocks[self.current_block_index - 1]
            if prev_block['speaker'] == speaker_idx:
                is_turn_start = False
        
        current_block['is_turn_start'] = is_turn_start
        
        for i in range(self.current_block_index + 1, len(self.srt_blocks)):
            if self.srt_blocks[i]['speaker'] == speaker_idx:
                self.srt_blocks[i]['is_turn_start'] = False
            else:
                break
        
        # Update the unassigned list immediately
        self.update_unassigned_list()  # We'll create this helper method
        
        if not (self.is_playing and self.auto_sync_enabled):
            self.find_next_unassigned()
            
        self.mark_unsaved_changes()

    def update_unassigned_list(self):
        """Update just the unassigned segments list (without full display refresh)"""
        self.unassigned_list.clear()
        unassigned_count = 0
        total_blocks = len(self.srt_blocks)
        
        for i, block in enumerate(self.srt_blocks):
            if block['speaker'] is None:
                unassigned_count += 1
                preview = block['text'][:50] + "..." if len(block['text']) > 50 else block['text']
                self.unassigned_list.addItem(f"{i+1}: {preview}")
        
        # Update label with counter
        self.unassigned_blocks_label.setText(f"Unassigned Segments ({unassigned_count}/{total_blocks}):")
        
    def unassign_current(self):
        if not self.srt_blocks:
            return
        self.push_undo()
            
        current_block = self.srt_blocks[self.current_block_index]
        current_block['speaker'] = None
        current_block['is_turn_start'] = True
        
        for i in range(self.current_block_index + 1, len(self.srt_blocks)):
            if i > 0 and self.srt_blocks[i]['speaker'] is not None:
                prev_speaker = self.srt_blocks[i-1]['speaker']
                current_speaker = self.srt_blocks[i]['speaker']
                self.srt_blocks[i]['is_turn_start'] = (prev_speaker != current_speaker)
        
        self.update_display()
        self.mark_unsaved_changes()
        
    def find_next_unassigned(self):
        start_index = self.current_block_index
        for i in range(1, len(self.srt_blocks) + 1):
            next_index = (start_index + i) % len(self.srt_blocks)
            if self.srt_blocks[next_index]['speaker'] is None:
                self.current_block_index = next_index
                self.update_display()
                return
        
        if self.current_block_index < len(self.srt_blocks) - 1:
            self.current_block_index += 1
            self.update_display()
            
    def split_current_block(self):
        if not self.srt_blocks:
            return
            
        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()
            
        current_block = self.srt_blocks[self.current_block_index]
        dialog = BlockSplitDialog(current_block['raw_text'], self)   # use raw_text
        
        if dialog.exec_() == QDialog.Accepted:
            self.push_undo()
            split_pos = dialog.split_position
            if 0 < split_pos < len(current_block['raw_text']):
                text_before = current_block['raw_text'][:split_pos].strip()
                text_after = current_block['raw_text'][split_pos:].strip()
                
                if text_before and text_after:
                    if current_block.get('start_time') and current_block.get('end_time'):
                        original_end_time = current_block['end_time']
                        original_end_ms = time_to_ms(original_end_time)
                        
                        start_ms = time_to_ms(current_block['start_time'])
                        end_ms = original_end_ms
                        total_duration = end_ms - start_ms
                        
                        total_chars = len(text_before) + len(text_after)
                        before_proportion = len(text_before) / total_chars

                        split_ms = start_ms + int(total_duration * before_proportion)
                        split_ms = max(start_ms + 100, min(end_ms - 100, split_ms))

                        current_block['raw_text'] = text_before
                        current_block['text'] = text_before   # also update text for compatibility
                        current_block['end_time'] = ms_to_time(split_ms)

                        new_block = current_block.copy()
                        new_block['raw_text'] = text_after
                        new_block['text'] = text_after
                        new_block['index'] = max(block['index'] for block in self.srt_blocks) + 1
                        new_block['start_time'] = ms_to_time(split_ms)
                        new_block['end_time'] = original_end_time
                        new_block['speaker'] = None
                        new_block['is_turn_start'] = False

                        if current_block['speaker'] is not None:
                            new_block['speaker'] = current_block['speaker']
                            new_block['is_turn_start'] = False
                    else:
                        current_block['raw_text'] = text_before
                        current_block['text'] = text_before

                        new_block = current_block.copy()
                        new_block['raw_text'] = text_after
                        new_block['text'] = text_after
                        new_block['index'] = max(block['index'] for block in self.srt_blocks) + 1
                        new_block['speaker'] = None
                        new_block['is_turn_start'] = False

                        if current_block['speaker'] is not None:
                            new_block['speaker'] = current_block['speaker']
                            new_block['is_turn_start'] = False

                    self.srt_blocks.insert(self.current_block_index + 1, new_block)
                    self.update_display()
                    self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def merge_with_next(self):
        if self.current_block_index >= len(self.srt_blocks) - 1:
            return
        self.push_undo()

        current_block = self.srt_blocks[self.current_block_index]
        next_block = self.srt_blocks[self.current_block_index + 1]

        if current_block['speaker'] is None or current_block['speaker'] == next_block['speaker']:
            # Merge raw texts
            current_block['raw_text'] += " " + next_block['raw_text']
            current_block['text'] = current_block['raw_text']   # sync text
            current_block['end_time'] = next_block['end_time']

            if next_block.get('is_turn_start', False):
                current_block['is_turn_start'] = True

            del self.srt_blocks[self.current_block_index + 1]
            self.update_display()
            self.mark_unsaved_changes()

    def edit_current_block(self):
        if not self.srt_blocks:
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        current_block = self.srt_blocks[self.current_block_index]
        dialog = RichEditDialog(current_block['raw_text'], self)   # use new dialog

        if dialog.exec_() == QDialog.Accepted:
            self.push_undo()
            new_text = dialog.get_text()
            current_block['raw_text'] = new_text
            current_block['text'] = new_text
            # Clear overlap_info if user removed overlap markers
            if current_block.get('overlap_info'):
                indent_ph = self.INDENT_PLACEHOLDER
                has_overlap = bool(re.search(re.escape(indent_ph), new_text))
                if not has_overlap:
                    del current_block['overlap_info']
            self.update_display()
            self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()
                
    def edit_current_timestamps(self):
        """Open dialog to edit start/end times of the current segment."""
        if not self.srt_blocks:
            return

        # Pause audio if autopause is enabled
        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        block = self.srt_blocks[self.current_block_index]
        start = block.get('start_time', '')
        end = block.get('end_time', '')

        dialog = EditTimestampsDialog(start, end, self)
        if dialog.exec_() == QDialog.Accepted:
            self.push_undo()
            new_start, new_end = dialog.get_times()
            # Update block
            block['start_time'] = new_start
            block['end_time'] = new_end
            # If timestamps are cleared, update file_has_timestamps? Probably not needed.
            self.update_display()
            self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def open_symbol_dialog(self):
        """Open the enhanced symbol dialog"""
        if not self.srt_blocks:
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        dialog = EnhancedSymbolDialog(self, initial_category=self.last_symbol_category)
        if dialog.exec_() == QDialog.Accepted:
            symbol_info = dialog.get_selected_symbol_info()
            self.handle_symbol_insertion(symbol_info)
            # Store the category that was just used
            self.last_symbol_category = dialog.current_category_index

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_gat2_symbol(self, option_index):
        """Handle GAT2 symbols by index."""
        symbols = ["(.)", "(-)", "(--)", "(---)", "(_._)", "(())", "<<>>", "[ ]", 
                   "°h", "°hh", "°hhh", "h°", "hh°", "hhh°"]
        if option_index == 4:          # measured pause (_._)
            self.handle_measured_pause()
        elif option_index == 5:        # comment (())
            self.handle_comment()
        elif option_index == 6:        # action <<>>
            self.handle_action()
        elif option_index == 7:        # overlap [ ]
            self.handle_overlap()
        else:                           # all other symbols (pauses, breaths)
            symbol = symbols[option_index]
            self.handle_pause(symbol)

    def handle_symbol_insertion(self, symbol_info):
        """Handle insertion of any symbol type"""
        category = symbol_info.get('category', '').lower()
        
        if category == 'dresing && pehl':
            self.handle_dresing_pehl_symbol(symbol_info)
        elif category == 'tiq':
            self.handle_tiq_symbol(symbol_info)
        elif category == 'custom':
            self.handle_custom_symbol(symbol_info)
        else:  # GAT2
            self.handle_gat2_symbol(symbol_info.get('index', 0))

    def handle_dresing_pehl_symbol(self, symbol_info):
        display = symbol_info.get('display', '')
        current_block = self.srt_blocks[self.current_block_index]

        if display in ["(.)", "(..)", "(...)"]:
            dialog = PlacementDialog(current_block['raw_text'], display, self, cjk_mode=self.cjk_mode)
            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                create_new, result = dialog.get_result()
                if create_new:
                    self.create_new_block_with_symbol(result)
                else:
                    current_block['raw_text'] = result
                    current_block['text'] = result
                self.update_display()
                self.mark_unsaved_changes()

        elif display == "(_)":
            seconds, ok = QInputDialog.getInt(
                self, "Measured Pause",
                "Enter pause length in seconds:",
                value=2, min=1, max=60
            )
            if ok:
                symbol = f"({seconds})"
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        # ... (overlap handler uses TextSelectionDialog, no change)
        elif display == "//":
            self.handle_dresing_overlap()

        elif display == "(   )":
            comment, ok = QInputDialog.getText(self, "Comment", "Enter comment:")
            if ok and comment:
                symbol = f"({comment})"
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        elif display == "⏱":
            default_time = ""
            if current_block.get('start_time'):
                time_str = current_block['start_time']
                if ',' in time_str:
                    time_str = time_str.split(',')[0]
                parts = time_str.split(':')
                if len(parts) == 3 and parts[0] == '00':
                    default_time = f"{parts[1]}:{parts[2]}"
                else:
                    default_time = time_str

            timestamp, ok = QInputDialog.getText(
                self, "Insert Timestamp",
                "Enter timestamp (e.g., 01:23):",
                text=default_time
            )
            if ok and timestamp:
                symbol = f"#{timestamp}#"
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()
                    
    def handle_dresing_overlap(self):
        """Handle Dresing & Pehl overlap marker // (similar to GAT2 overlap)"""
        if not self.srt_blocks or self.current_block_index == 0:
            QMessageBox.information(self, "Overlap Feature",
                                   "Overlap requires at least two consecutive blocks.")
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        current_block = self.srt_blocks[self.current_block_index]
        prev_block = self.srt_blocks[self.current_block_index - 1]

        # Ensure raw_text exists
        if 'raw_text' not in current_block:
            current_block['raw_text'] = current_block['text']
        if 'raw_text' not in prev_block:
            prev_block['raw_text'] = prev_block['text']

        # Select overlapping text in current block
        dialog = TextSelectionDialog(current_block['raw_text'], self)
        dialog.setWindowTitle("Select Overlapping Text in Current Block")
        if dialog.exec_() == QDialog.Accepted:
            start_pos, end_pos, selected_text = dialog.get_selection()
            if selected_text:
                # Select overlapping text in previous block
                prev_dialog = TextSelectionDialog(prev_block['raw_text'], self)
                prev_dialog.setWindowTitle("Select Overlapping Text in Previous Block")
                if prev_dialog.exec_() == QDialog.Accepted:
                    prev_start, prev_end, prev_selected = prev_dialog.get_selection()
                    if prev_selected:
                        self.push_undo()
                        # For Dresing & Pehl, we just insert // markers without indentation.
                        prev_before = prev_block['raw_text'][:prev_start]
                        prev_after = prev_block['raw_text'][prev_end:]
                        prev_block['raw_text'] = f"{prev_before}//{prev_selected}//{prev_after}"
                        prev_block['text'] = prev_block['raw_text']

                        curr_before = current_block['raw_text'][:start_pos]
                        curr_after = current_block['raw_text'][end_pos:]
                        current_block['raw_text'] = f"{curr_before}//{selected_text}//{curr_after}"
                        current_block['text'] = current_block['raw_text']

                        self.update_display()
                        self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()
     
    def handle_tiq_overlap(self):
        if not self.srt_blocks or self.current_block_index == 0:
            QMessageBox.information(self, "Overlap Feature",
                                   "Overlap requires at least two consecutive blocks.")
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        current_block = self.srt_blocks[self.current_block_index]
        prev_block = self.srt_blocks[self.current_block_index - 1]

        if 'raw_text' not in current_block:
            current_block['raw_text'] = current_block['text']
        if 'raw_text' not in prev_block:
            prev_block['raw_text'] = prev_block['text']

        curr_dialog = TextSelectionDialog(current_block['raw_text'], self)
        curr_dialog.setWindowTitle("Select Overlapping Text in Later Block")
        if curr_dialog.exec_() == QDialog.Accepted:
            curr_start, curr_end, curr_selected = curr_dialog.get_selection()
            if curr_selected:
                self.push_undo()
                prev_dialog = TextSelectionDialog(prev_block['raw_text'], self)
                prev_dialog.setWindowTitle("Select Overlapping Text in Earlier Block")
                if prev_dialog.exec_() == QDialog.Accepted:
                    prev_start, prev_end, prev_selected = prev_dialog.get_selection()
                    if prev_selected:
                        # For TiQ, advance prev_start past any whitespace so the └
                        # points at the first character of the overlapped word,
                        # not at a space before it.
                        prev_block_text = prev_block['raw_text']
                        while prev_start < len(prev_block_text) and prev_block_text[prev_start] in (' ', '\t'):
                            prev_start += 1
                        viewer_indent = prev_start
                        curr_before = current_block['raw_text'][:curr_start]
                        curr_after = current_block['raw_text'][curr_end:]
                        indent_placeholders = self.INDENT_PLACEHOLDER * viewer_indent
                        current_block['raw_text'] = f"{curr_before}{indent_placeholders}└{curr_selected}{curr_after}"
                        current_block['text'] = current_block['raw_text']
                        current_block.pop('is_empty', None)
                        current_block['overlap_info'] = {
                            'indent': prev_start,
                            'overlap_text': f"└{curr_selected}",
                            'prev_block_idx': self.current_block_index - 1,
                            'convention': 'tiq',
                            'text_before': curr_before.strip(),
                            'text_after': curr_after.strip()
                        }
                        self.update_display()
                        self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_tiq_symbol(self, symbol_info):
        display = symbol_info.get('display', '')
        current_block = self.srt_blocks[self.current_block_index]

        if display == "(.)":
            dialog = PlacementDialog(current_block['raw_text'], "(.)", self, cjk_mode=self.cjk_mode)
            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                create_new, result = dialog.get_result()
                if create_new:
                    self.create_new_block_with_symbol(result)
                else:
                    current_block['raw_text'] = result
                    current_block['text'] = result
                self.update_display()
                self.mark_unsaved_changes()

        elif display == "(_)":
            seconds, ok = QInputDialog.getInt(
                self, "Measured Pause",
                "Enter pause length in seconds:",
                value=2, min=1, max=60
            )
            if ok:
                symbol = f"({seconds})"
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        elif display == "(())":
            comment, ok = QInputDialog.getText(self, "Comment", "Enter comment:")
            if ok and comment:
                symbol = f"(({comment}))"
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        elif display == "└":
            self.handle_tiq_overlap()
            self.update_display()
            self.mark_unsaved_changes()

        elif display == "@(.)@":
            dialog = PlacementDialog(current_block['raw_text'], "@(.)@", self, cjk_mode=self.cjk_mode)
            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                create_new, result = dialog.get_result()
                if create_new:
                    self.create_new_block_with_symbol(result)
                else:
                    current_block['raw_text'] = result
                    current_block['text'] = result
                self.update_display()
                self.mark_unsaved_changes()

        elif display == "@(_)@":
            seconds, ok = QInputDialog.getInt(
                self, "Laughing Duration",
                "Enter laughter duration in seconds:",
                value=2, min=1, max=10
            )
            if ok:
                symbol = f"@({seconds}s)@"
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        elif display in ["@(   )@", "°   °", "//   //"]:
            was_playing = False
            if self.auto_pause_enabled and self.is_playing:
                was_playing = True
                if self.audio_player:
                    self.audio_player.pause()

            # Determine left/right markers
            if display == "@(   )@":
                left, right = "@(", ")@"
            elif display == "°   °":
                left, right = "°", "°"
            else:  # "//   //"
                left, right = "//", "//"

            dialog = TextSelectionDialog(current_block['raw_text'], self)
            dialog.setWindowTitle(f"Select text for {display}")
            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                start_pos, end_pos, selected_text = dialog.get_selection()
                if selected_text:
                    new_raw = (current_block['raw_text'][:start_pos] +
                               left + selected_text + right +
                               current_block['raw_text'][end_pos:])
                    current_block['raw_text'] = new_raw
                    current_block['text'] = new_raw
                    self.update_display()
                    self.mark_unsaved_changes()

            if was_playing and self.auto_pause_enabled:
                if self.audio_player:
                    self.audio_player.play()


    def handle_custom_symbol(self, symbol_info):
        symbol_type = symbol_info.get('type', 'simple')
        current_block = self.srt_blocks[self.current_block_index]

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        if symbol_type == 'simple':
            symbol = symbol_info.get('display', '')
            dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                create_new, result = dialog.get_result()
                if create_new:
                    self.create_new_block_with_symbol(result)
                else:
                    current_block['raw_text'] = result
                    current_block['text'] = result
                self.update_display()
                self.mark_unsaved_changes()

        elif symbol_type == 'wrapper':
            left = symbol_info.get('left', '')
            right = symbol_info.get('right', '')
            dialog = TextSelectionDialog(current_block['raw_text'], self)
            dialog.setWindowTitle("Select text to wrap")
            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                start_pos, end_pos, selected_text = dialog.get_selection()
                if selected_text:
                    new_raw = (current_block['raw_text'][:start_pos] +
                               left + selected_text + right +
                               current_block['raw_text'][end_pos:])
                    current_block['raw_text'] = new_raw
                    current_block['text'] = new_raw
                    self.update_display()
                    self.mark_unsaved_changes()

        elif symbol_type == 'comment':
            left = symbol_info.get('left', '')
            right = symbol_info.get('right', '')
            comment, ok = QInputDialog.getText(self, "Comment", "Enter comment:")
            if ok and comment:
                symbol = left + comment + right
                dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)
                if dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        elif symbol_type == 'comment_reach':
            left = symbol_info.get('left', '')
            right_action = symbol_info.get('right', '')
            right_segment = symbol_info.get('segment_right', '')

            select_dialog = TextSelectionDialog(current_block['raw_text'], self)
            select_dialog.setWindowTitle("Select spoken text to annotate")
            if select_dialog.exec_() == QDialog.Accepted:
                start_pos, end_pos, selected_text = select_dialog.get_selection()
                if selected_text:
                    description, ok = QInputDialog.getText(self, "Action Description",
                                                           "Enter description for the action/comment:")
                    if ok and description:
                        wrapped = left + description + right_action + selected_text + right_segment
                        new_raw = (current_block['raw_text'][:start_pos] +
                                   wrapped +
                                   current_block['raw_text'][end_pos:])
                        current_block['raw_text'] = new_raw
                        current_block['text'] = new_raw
                        self.update_display()
                        self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()
            
    def create_new_block_with_symbol(self, symbol_text):
        """Create a new block containing just the symbol"""
        new_block = {
            'index': max(block['index'] for block in self.srt_blocks) + 1,
            'start_time': '',
            'end_time': '',
            'text': symbol_text,
            'raw_text': symbol_text,
            'speaker': None,
            'is_turn_start': False,
            'is_pause': True,
        }
        self.srt_blocks.insert(self.current_block_index + 1, new_block)
        self.update_display()
        self.mark_unsaved_changes()

    # Update the existing open_pause_dialog method to call the new one
    def open_pause_dialog(self):
        """Legacy method - calls the new enhanced dialog"""
        self.open_symbol_dialog()

    def handle_measured_pause(self):
        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        time_ms, ok = QInputDialog.getInt(
            self,
            "Measured Pause",
            "Enter pause length in 100 milliseconds (e.g., 8 for 0.8 seconds):",
            value=5, min=1, max=50, step=1
        )

        if ok:
            seconds = time_ms / 10.0
            symbol = f"({seconds:.1f})"

            current_block = self.srt_blocks[self.current_block_index]
            dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)

            if dialog.exec_() == QDialog.Accepted:
                self.push_undo()
                create_new, result = dialog.get_result()
                if create_new:
                    self.create_new_block_with_symbol(result)
                else:
                    current_block['raw_text'] = result
                    current_block['text'] = result
                self.update_display()
                self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_pause(self, symbol):
        if not self.srt_blocks:
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        current_block = self.srt_blocks[self.current_block_index]
        dialog = PlacementDialog(current_block['raw_text'], symbol, self, cjk_mode=self.cjk_mode)

        if dialog.exec_() == QDialog.Accepted:
            self.push_undo()
            create_new, result = dialog.get_result()
            if create_new:
                self.create_new_block_with_symbol(result)
            else:
                current_block['raw_text'] = result
                current_block['text'] = result
            self.update_display()
            self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()
                    
    def handle_comment(self):
        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        dialog = CommentDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            comment = dialog.get_comment()
            if comment:
                current_block = self.srt_blocks[self.current_block_index]
                placement_dialog = PlacementDialog(current_block['raw_text'], comment, self, cjk_mode=self.cjk_mode)

                if placement_dialog.exec_() == QDialog.Accepted:
                    self.push_undo()
                    create_new, result = placement_dialog.get_result()
                    if create_new:
                        self.create_new_block_with_symbol(result)
                    else:
                        current_block['raw_text'] = result
                        current_block['text'] = result
                    self.update_display()
                    self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_action(self):
        if not self.srt_blocks:
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        current_block = self.srt_blocks[self.current_block_index]
        dialog = TextSelectionDialog(current_block['raw_text'], self)

        if dialog.exec_() == QDialog.Accepted:
            start_pos, end_pos, selected_text = dialog.get_selection()
            if selected_text:
                action_text, ok = QInputDialog.getText(self, "Action Description",
                                                     f"Describe the action for '{selected_text}':")
                if ok and action_text:
                    self.push_undo()
                    before_text = current_block['raw_text'][:start_pos]
                    after_text = current_block['raw_text'][end_pos:]
                    new_raw = f"{before_text}<<{action_text}> {selected_text}>{after_text}"
                    current_block['raw_text'] = new_raw
                    current_block['text'] = new_raw
                    self.update_display()
                    self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_overlap(self):
        """GAT2 overlap: both blocks get brackets, and later block gets indentation."""
        if not self.srt_blocks or self.current_block_index == 0:
            QMessageBox.information(self, "Overlap Feature",
                                   "Overlap requires at least two consecutive blocks.")
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        current_block = self.srt_blocks[self.current_block_index]
        prev_block = self.srt_blocks[self.current_block_index - 1]

        # Ensure raw_text exists
        if 'raw_text' not in current_block:
            current_block['raw_text'] = current_block['text']
        if 'raw_text' not in prev_block:
            prev_block['raw_text'] = prev_block['text']

        # Select overlapping text in current block
        curr_dialog = TextSelectionDialog(current_block['raw_text'], self)
        curr_dialog.setWindowTitle("Select Overlapping Text in Current Block")
        if curr_dialog.exec_() == QDialog.Accepted:
            curr_start, curr_end, curr_selected = curr_dialog.get_selection()
            if curr_selected:
                # Select overlapping text in previous block
                prev_dialog = TextSelectionDialog(prev_block['raw_text'], self)
                prev_dialog.setWindowTitle("Select Overlapping Text in Previous Block")
                if prev_dialog.exec_() == QDialog.Accepted:
                    prev_start, prev_end, prev_selected = prev_dialog.get_selection()
                    if prev_selected:
                        self.push_undo()
                        # Modify previous block: insert brackets around the overlapping text
                        prev_before = prev_block['raw_text'][:prev_start]
                        prev_after = prev_block['raw_text'][prev_end:]
                        prev_block['raw_text'] = f"{prev_before}[{prev_selected}]{prev_after}"
                        prev_block['text'] = prev_block['raw_text']

                        # Block-level indent for viewer. Export will compute wrapping-aware indent.
                        viewer_indent = len(prev_before)
                        curr_before = current_block['raw_text'][:curr_start]
                        curr_after = current_block['raw_text'][curr_end:]
                        indent_placeholders = self.INDENT_PLACEHOLDER * viewer_indent
                        current_block['raw_text'] = f"{curr_before}{indent_placeholders}[{curr_selected}]{curr_after}"
                        current_block['text'] = current_block['raw_text']
                        current_block.pop('is_empty', None)  # clear stale is_empty flag
                        current_block['overlap_info'] = {
                            'indent': viewer_indent,
                            'overlap_text': f"[{curr_selected}]",
                            'prev_block_idx': self.current_block_index - 1,
                            'convention': 'gat2',
                            'text_before': curr_before.strip(),
                            'text_after': curr_after.strip()
                        }

                        self.update_display()
                        self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def _detect_old_overlap_blocks(self):
        """Scan srt_blocks for inline overlap placeholders without overlap_info metadata.
        
        Returns a list of (block_index, block) tuples for blocks that have
        ␣ placeholders suggesting old-format overlap but no overlap_info.
        """
        old_blocks = []
        for idx, block in enumerate(self.srt_blocks):
            raw = block.get('raw_text', '')
            if not raw:
                continue
            if self.INDENT_PLACEHOLDER in raw and not block.get('overlap_info'):
                has_gat2_overlap = re.search(
                    re.escape(self.INDENT_PLACEHOLDER) + r'+\[', raw
                )
                has_tiq_overlap = re.search(
                    re.escape(self.INDENT_PLACEHOLDER) + r'+└', raw
                )
                if has_gat2_overlap or has_tiq_overlap:
                    old_blocks.append((idx, block))
        return old_blocks

    def _upgrade_old_overlap_format(self, old_blocks):
        """Reconstruct overlap_info metadata from inline placeholders in old-format blocks."""
        import re as _re
        count = 0
        for idx, block in old_blocks:
            raw = block.get('raw_text', '')
            if not raw:
                continue

            ph_esc = _re.escape(self.INDENT_PLACEHOLDER)
            tiq_match = _re.search(ph_esc + r'+(└)', raw)
            gat2_match = _re.search(ph_esc + r'+(\[)', raw)

            if tiq_match:
                ph_start = tiq_match.start()
                indent = raw[ph_start:tiq_match.start(1)].count(self.INDENT_PLACEHOLDER)
                text_before = raw[:ph_start].strip()
                overlap_text = raw[tiq_match.start(1):]
                
                prev_idx = idx - 1
                while prev_idx >= 0:
                    prev_block = self.srt_blocks[prev_idx]
                    if prev_block.get('speaker') is not None:
                        break
                    prev_idx -= 1
                
                block['overlap_info'] = {
                    'indent': indent,
                    'overlap_text': overlap_text,
                    'prev_block_idx': prev_idx if prev_idx >= 0 else None,
                    'convention': 'tiq',
                    'text_before': text_before,
                    'text_after': ''
                }
                count += 1

            elif gat2_match:
                ph_start = gat2_match.start()
                bracket_start = gat2_match.start(1)
                indent = raw[ph_start:bracket_start].count(self.INDENT_PLACEHOLDER)
                text_before = raw[:ph_start].strip()
                close_bracket = raw.find(']', bracket_start)
                if close_bracket == -1:
                    continue
                overlap_text = raw[bracket_start:close_bracket + 1]
                text_after = raw[close_bracket + 1:].strip()
                
                prev_idx = idx - 1
                while prev_idx >= 0:
                    prev_block = self.srt_blocks[prev_idx]
                    if prev_block.get('speaker') is not None:
                        break
                    prev_idx -= 1
                
                block['overlap_info'] = {
                    'indent': indent,
                    'overlap_text': overlap_text,
                    'prev_block_idx': prev_idx if prev_idx >= 0 else None,
                    'convention': 'gat2',
                    'text_before': text_before,
                    'text_after': text_after
                }
                count += 1

        return count

    def _check_and_upgrade_old_overlap_format(self):
        """Check if loaded project has old-format overlap blocks and offer to upgrade."""
        old_blocks = self._detect_old_overlap_blocks()
        if not old_blocks:
            return

        reply = QMessageBox.question(
            self,
            "Overlap Format Update Available",
            "This project file was created with an older version of CapsQual.\n\n"
            "The way overlapping speech is handled has been improved:\n"
            "• Overlap indentation now correctly accounts for concatenated turns and line wrapping.\n"
            "• Older projects show the indentation correctly in the editor, but the export may not\n"
            "  display overlap indentation properly.\n\n"
            f"Found {len(old_blocks)} block(s) with old-format overlap markers.\n\n"
            "Do you want CapsQual to automatically update this file to the new format?\n"
            "The file will be updated in memory — you will need to save it afterwards.\n\n"
            "If you choose 'No', the file will be loaded as-is, but overlap may not export correctly.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        upgraded_count = self._upgrade_old_overlap_format(old_blocks)
        if upgraded_count > 0:
            self.mark_unsaved_changes()
            QMessageBox.information(
                self,
                "Overlap Format Updated",
                f"Successfully updated {upgraded_count} block(s) to the new overlap format.\n\n"
                "Please review the overlap positions and save the project to make the changes permanent."
            )

    def remove_overlap_from_current(self):
        """Remove overlap markers and metadata from the current block."""
        if not self.srt_blocks:
            return
        block = self.srt_blocks[self.current_block_index]
        if not block.get('overlap_info'):
            QMessageBox.information(self, "No Overlap", "The current block does not contain an overlap.")
            return

        self.push_undo()
        raw = block['raw_text']
        info = block['overlap_info']
        overlap_text = info.get('overlap_text', '')
        if info.get('convention') == 'tiq':
            # TiQ format: ␣␣␣└selected_text
            marker_idx = raw.find('└')
            if marker_idx >= 0:
                before = raw[:marker_idx]
                before_clean = before.rstrip(self.INDENT_PLACEHOLDER)
                overlap_content = overlap_text[1:] if overlap_text.startswith('└') else overlap_text
                end_idx = marker_idx + len(overlap_text)
                after = raw[end_idx:] if end_idx < len(raw) else ''
                # Reconstruct: keep the overlap content, remove markers/placeholders
                raw = before_clean + overlap_content + after
        elif info.get('convention') == 'gat2':
            # GAT2 format: ␣␣␣[selected_text]
            marker_idx = raw.find('[')
            if marker_idx >= 0:
                before = raw[:marker_idx]
                before_clean = before.rstrip(self.INDENT_PLACEHOLDER)
                if overlap_text.startswith('[') and overlap_text.endswith(']'):
                    overlap_content = overlap_text[1:-1]
                else:
                    overlap_content = overlap_text
                end_idx = marker_idx + len(overlap_text)
                after = raw[end_idx:] if end_idx < len(raw) else ''
                # Reconstruct: keep the overlap content, remove markers/placeholders
                raw = before_clean + overlap_content + after

        block['raw_text'] = raw
        block['text'] = raw
        del block['overlap_info']
        self.update_display()
        self.mark_unsaved_changes()

    def insert_empty_line(self):
        """Insert an empty line after current block and try to set timestamps from neighbors."""
        if not self.srt_blocks:
            return
        self.push_undo()

        current_idx = self.current_block_index
        current_block = self.srt_blocks[current_idx]

        # Determine if there is a next block (before insertion)
        has_next = current_idx + 1 < len(self.srt_blocks)
        next_block = self.srt_blocks[current_idx + 1] if has_next else None

        # Create new empty block
        new_block = {
            'index': max(block['index'] for block in self.srt_blocks) + 1,
            'start_time': '',
            'end_time': '',
            'text': '',
            'raw_text': '',
            'speaker': None,
            'is_turn_start': False,
            'is_empty': True,
        }

        # Insert the new block
        self.srt_blocks.insert(current_idx + 1, new_block)

        # Try to set timestamps based on neighbors
        prev_end = current_block.get('end_time')
        next_start = next_block.get('start_time') if next_block else None

        if prev_end and next_start:
            # Both neighbors have timestamps – set a proper interval
            new_block['start_time'] = prev_end
            new_block['end_time'] = next_start
        elif prev_end and not next_start:
            # Only previous end time – set start only (user can adjust later)
            new_block['start_time'] = prev_end
            # end_time remains empty
        elif not prev_end and next_start:
            # Only next start time – set end only
            new_block['end_time'] = next_start
            # start_time remains empty
        # else both empty – leave empty

        # Move to the new block
        self.current_block_index = current_idx + 1

        self.update_display()
        self.mark_unsaved_changes()

    def jump_to_block(self, item):
        text = item.text()
        match = re.match(r'(\d+):', text)
        if match:
            block_idx = int(match.group(1)) - 1
            if 0 <= block_idx < len(self.srt_blocks):
                self.current_block_index = block_idx
                self.update_display()

    def save_project(self, force_save_as=False):
        if not self.srt_blocks:
            return

        file_path = None
        default_name = ""

        # --- Determine if we should show a Save As dialog ---
        if not force_save_as and self.current_file_path:
            # If current file is a .capsgat file, handle upgrade
            if self.current_file_path.endswith('.capsgat'):
                reply = QMessageBox.question(
                    self,
                    "Project Format Update",
                    "This project was created with the older CapsGAT format (.capsgat).\n\n"
                    "To save it, you must use the new CapsQual format (.capsqual).\n"
                    "Would you like to save it as .capsqual now? (You will be prompted for a new filename.)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.No:
                    return  # user cancelled save

                # Build default save path in the same directory as the old file
                old_dir = os.path.dirname(self.current_file_path)
                base = os.path.basename(self.current_file_path)[:-8]  # remove '.capsgat'
                default_name = os.path.join(old_dir, base + '.capsqual')
                force_save_as = True   # force dialog
            elif self.current_file_path.endswith('.capsqual'):
                # It's a valid CapsQual project file – use it
                file_path = self.current_file_path
            else:
                # Current file is a subtitle or other format – treat as unsaved
                force_save_as = True

        # --- If we need a Save As dialog, show it ---
        if force_save_as or not file_path:
            # Compute a default name if not already set
            if not default_name:
                if self.project_name:
                    default_name = self.project_name.replace(" ", "_") + ".capsqual"
                elif self.current_file_path:
                    # For existing non-capsqual file, use its directory with new extension
                    default_name = str(Path(self.current_file_path).with_suffix('.capsqual'))
                else:
                    default_name = "transcript_project.capsqual"
                # Prepend base directory to bare filenames
                if default_name and not os.path.dirname(default_name):
                    base = self._base_dir_for_dialog()
                    if base:
                        default_name = os.path.join(base, default_name)

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Project As",
                default_name,
                "CapsQual Project (*.capsqual);;All Files (*)"
            )
            if not file_path:
                return  # user cancelled

            # Ensure the file has .capsqual extension
            if not file_path.endswith('.capsqual'):
                file_path += '.capsqual'

        # --- Save the project ---
        try:
            project_data = {
                'srt_blocks': self.srt_blocks,
                'current_block_index': self.current_block_index,
                'speakers': self.speakers,
                # Save the original source path if we have it, otherwise the current file path
                'source_file': getattr(self, 'source_file', self.current_file_path),
                'file_has_timestamps': self.file_has_timestamps,
                'audio_file_path': self.audio_file_path,
                'project_name': self.project_name,
                'project_memo': self.project_memo,
                'text_display_font': {
                    'family': self.text_display_font.family(),
                    'size': self.text_display_font.pointSize()
                },
                'playback_speed': self.playback_speed,
                'cjk_mode': self.cjk_mode,
                'timestamp_style': self.timestamp_style,
                'custom_timestamp_pattern': self.custom_timestamp_pattern
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)

            self.current_file_path = file_path
            self.add_to_recent(file_path)
            self.clear_unsaved_changes()
            QMessageBox.information(self, "Success", f"Project saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save project: {str(e)}")


    def export_transcript(self):
        
        if not self.srt_blocks:
            return

        project_info = {
            'name': self.project_name,
            'memo': self.project_memo
        }

        preview_dialog = ExportPreviewDialog(
            self,
            has_timestamps=self.file_has_timestamps,
            timestamp_style=self.timestamp_style,
            custom_pattern=self.custom_timestamp_pattern,
            project_info=project_info,
            audio_path=self.audio_file_path
        )
        if preview_dialog.exec_() == QDialog.Accepted:
            settings = preview_dialog.get_export_settings()

            unassigned_handling = "skip"
            if settings['format'] == 'srt':
                unassigned_count = sum(1 for block in self.srt_blocks
                                     if block['speaker'] is None and not block.get('is_pause')
                                     and not block.get('is_comment') and not block.get('is_empty'))

                if unassigned_count > 0:
                    dialog = UnassignedSegmentsDialog(unassigned_count, self)
                    if dialog.exec_() == QDialog.Accepted:
                        unassigned_handling = dialog.get_selected_option()
                    else:
                        return
                else:
                    unassigned_handling = "skip"

            if settings['format'] == 'srt':
                transcript_text = generate_srt_text(self.transcript,
                    include_diarization=settings['include_diarization'],
                    unassigned_handling=unassigned_handling
                )
            else:
                transcript_text = generate_transcript_text(self.transcript,
                    include_timestamps=settings['include_timestamps'],
                    timestamp_style=settings.get('timestamp_style', 'hash'),
                    custom_pattern=settings.get('custom_timestamp_pattern', None),
                    convention=settings['convention'],
                    include_diarization=settings['include_diarization'],
                    wrap_enabled=settings['wrap_enabled'],
                    wrap_length=settings['wrap_length'],
                    character_wrap=settings['character_wrap'],
                    add_blank_line=settings.get('add_blank_line', False),
                    concatenate_turns=settings.get('concatenate_turns', False),
                    delimiter_choice=settings.get('delimiter_choice', 'space'),
                    custom_delimiter=settings.get('custom_delimiter', '')
                )

            self.final_export(transcript_text, settings, project_info, unassigned_handling)


        
    
    


        








    def final_export(self, transcript_text, settings, project_info, unassigned_handling="skip"):
        format_extensions = {
            'html': '.html',
            'txt': '.txt',
            'srt': '.srt',
            'docx': '.docx'
        }

        file_ext = format_extensions.get(settings['format'], '.txt')

        default_name = ""
        if project_info.get('name'):
            default_name = project_info['name'].replace(" ", "_")
        else:
            default_name = "transcript"

        # Convention suffix map: internal name → filename tag
        convention_suffixes = {
            'gat2': '_gat',
            'tiq': '_tiq',
            'dresing_pehl': '_dp',
        }
        suffix = convention_suffixes.get(settings['convention'], '')
        if suffix:
            default_name += suffix

        default_name += file_ext

        # Prepend base directory to bare filenames
        if default_name and not os.path.dirname(default_name):
            base = self._base_dir_for_dialog()
            if base:
                default_name = os.path.join(base, default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export Transcript", default_name,
            f"{settings['format'].upper()} Files (*{file_ext})"
        )

        if not file_path:
            return

        try:
            if settings['format'] == 'srt':
                write_srt_file(transcript_text, file_path)
                QMessageBox.information(self, "Success", f"Transcript exported to {file_path}")

            elif settings['format'] == 'docx':
                result = write_docx_file(
                    transcript_text, settings, project_info,
                    self.audio_file_path, file_path
                )
                if result:
                    QMessageBox.information(self, "Success", f"Transcript exported to {file_path}")
                else:
                    # Fallback to plain text with .txt extension
                    new_path = os.path.splitext(file_path)[0] + '.txt'
                    QMessageBox.warning(
                        self,
                        "DOCX Export Failed",
                        f"python-docx library not found.\n\n"
                        f"Exporting as plain text instead.\n\n"
                        f"Saved as: {new_path}"
                    )
                    write_txt_file(transcript_text, new_path)

            elif settings['format'] == 'html':
                html_content = build_html_content(
                    transcript_text, settings, project_info, self.audio_file_path
                )
                write_html_file(html_content, file_path)
                QMessageBox.information(self, "Success", f"Transcript exported to {file_path}")

            else:  # plain text
                write_txt_file(transcript_text, file_path)
                QMessageBox.information(self, "Success", f"Transcript exported to {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not export file: {str(e)}")
        
    def closeEvent(self, event):
        """Clean up on close"""
        if self.audio_player:
            self.audio_player.cleanup()

        if self.check_unsaved_changes():
            event.accept()
        else:
            event.ignore()



