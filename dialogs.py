"""Dialog windows for CapsQual."""
import html
import os
import json
import re
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QDialogButtonBox,
    QPushButton, QLineEdit, QWidget, QMessageBox, QComboBox, QStackedWidget,
    QScrollArea, QFrame, QSizePolicy, QGridLayout, QFileDialog, QCheckBox,
    QRadioButton, QGroupBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QShortcut, QFontDialog, QFormLayout, QApplication
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence

from widgets import ThemeToggle

from utils import logger
from highlighting import FormattingMarkerHighlighter
from generators import (
    generate_srt_text, generate_transcript_text, strip_markup
)
from export import build_html_content



def _is_dark_theme(widget):
    """Check whether *widget* is using the dark palette via its QPalette."""
    return widget.palette().window().color().lightness() < 128






class TextSelectionDialog(QDialog):
    def __init__(self, block_text, parent=None):
        super().__init__(parent)
        self.block_text = block_text
        self.start_pos = 0
        self.end_pos = 0
        self.dark = _is_dark_theme(self)
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Select Text")
        self.setGeometry(300, 300, 700, 300)
        layout = QVBoxLayout(self)
        
        instructions = QLabel("Use ← → arrows to adjust selection, Shift+arrows to extend, then press Enter:")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setMaximumHeight(100)
        self.text_display.setStyleSheet("font-family: monospace; font-size: 14px;")
        self.highlighter = FormattingMarkerHighlighter(self.text_display.document())
        layout.addWidget(self.text_display)
        
        
        self.selection_label = QLabel("Selection: (none)")
        layout.addWidget(self.selection_label)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        for button in button_box.buttons():
            button.setFocusPolicy(Qt.NoFocus)
            
        layout.addWidget(button_box)
        
        self.update_display()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left and not event.modifiers() & Qt.ShiftModifier:
            if self.start_pos > 0:
                self.start_pos -= 1
                self.end_pos = self.start_pos
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Right and not event.modifiers() & Qt.ShiftModifier:
            if self.end_pos < len(self.block_text):
                self.start_pos += 1
                self.end_pos = self.start_pos
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Left and event.modifiers() & Qt.ShiftModifier:
            if self.start_pos > 0:
                self.start_pos -= 1
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Right and event.modifiers() & Qt.ShiftModifier:
            if self.end_pos < len(self.block_text):
                self.end_pos += 1
            self.update_display()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def update_display(self):
        before_text = self.block_text[:self.start_pos]
        selected_text = self.block_text[self.start_pos:self.end_pos]
        after_text = self.block_text[self.end_pos:]

        if self.dark:
            text_bg = "#3a3a3a"
            sel_bg = "#5a4a20"
        else:
            text_bg = "#e0e0e0"
            sel_bg = "#ffcc00"

        html_content = f"""
        <div style="font-family: monospace; font-size: 14px; padding: 10px;">
            <span style="background-color: {text_bg}; padding: 5px; border-radius: 3px;">{html.escape(before_text)}</span>
            <span style="background-color: {sel_bg}; padding: 5px; border-radius: 3px;">{html.escape(selected_text)}</span>
            <span style="background-color: {text_bg}; padding: 5px; border-radius: 3px;">{html.escape(after_text)}</span>
        </div>
        """
        
        self.text_display.setHtml(html_content)
        
        if self.start_pos == self.end_pos:
            self.selection_label.setText(f"Selection: (none) - Position: {self.start_pos}")
        else:
            self.selection_label.setText(f"Selection: '{html.escape(selected_text)}' (positions {self.start_pos}-{self.end_pos})")
    
    def get_selection(self):
        return self.start_pos, self.end_pos, self.block_text[self.start_pos:self.end_pos]

class BlockSplitDialog(QDialog):
    def __init__(self, block_text, parent=None):
        super().__init__(parent)
        self.block_text = block_text
        self.split_position = 0
        self.dark = _is_dark_theme(self)
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Split Block")
        self.setGeometry(300, 300, 700, 250)
        
        layout = QVBoxLayout(self)
        
        instructions = QLabel("Use ← → arrows to position split, then press Enter to confirm:")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setMaximumHeight(100)
        self.text_display.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(self.text_display)
        
        self.cursor_label = QLabel("Split position: 0")
        layout.addWidget(self.cursor_label)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        for button in button_box.buttons():
            button.setFocusPolicy(Qt.NoFocus)
            
        layout.addWidget(button_box)
        
        self.update_display()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.split_position = max(0, self.split_position - 1)
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Right:
            self.split_position = min(len(self.block_text), self.split_position + 1)
            self.update_display()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.accept()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def update_display(self):
        before_text = self.block_text[:self.split_position]
        after_text = self.block_text[self.split_position:]

        if self.dark:
            before_bg = "#3a5a3a"
            after_bg = "#5a3a3a"
        else:
            before_bg = "#c8f7c8"
            after_bg = "#f7c8c8"

        html_content = f"""
        <div style="font-family: monospace; font-size: 14px; padding: 10px;">
            <span style="background-color: {before_bg}; padding: 5px; border-radius: 3px;">{html.escape(before_text)}</span>
            <span style="background-color: {after_bg}; padding: 5px; border-radius: 3px;">{html.escape(after_text)}</span>
        </div>
        """
        
        self.text_display.setHtml(html_content)
        self.cursor_label.setText(f"Split position: {self.split_position} (text will be split after character {self.split_position})")

class EditTimestampsDialog(QDialog):
    def __init__(self, start_time="", end_time="", parent=None):
        super().__init__(parent)
        self.start_time = start_time
        self.end_time = end_time
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Edit Segment Timestamps")
        self.setGeometry(300, 300, 350, 200)

        layout = QVBoxLayout(self)

        # Checkbox to enable/disable timestamps
        self.enable_check = QCheckBox("Set timestamps for this segment")
        self.enable_check.setChecked(bool(self.start_time or self.end_time))
        self.enable_check.toggled.connect(self.on_enable_toggled)
        layout.addWidget(self.enable_check)

        # Create spin boxes for start time with labels above
        start_group = QGroupBox("Start Time")
        start_layout = QVBoxLayout()

        # Labels row – each label has fixed width matching its spin box
        labels_layout = QHBoxLayout()
        lbl_h = QLabel("HH")
        lbl_h.setFixedWidth(80)
        lbl_h.setAlignment(Qt.AlignCenter)
        labels_layout.addWidget(lbl_h)

        lbl_m = QLabel("mm")
        lbl_m.setFixedWidth(80)
        lbl_m.setAlignment(Qt.AlignCenter)
        labels_layout.addWidget(lbl_m)

        lbl_s = QLabel("ss")
        lbl_s.setFixedWidth(80)
        lbl_s.setAlignment(Qt.AlignCenter)
        labels_layout.addWidget(lbl_s)

        lbl_ms = QLabel("SSS")
        lbl_ms.setFixedWidth(90)
        lbl_ms.setAlignment(Qt.AlignCenter)
        labels_layout.addWidget(lbl_ms)

        labels_layout.addStretch()
        start_layout.addLayout(labels_layout)

        # Spin boxes row
        spins_layout = QHBoxLayout()
        self.start_h = QSpinBox()
        self.start_h.setRange(0, 99)
        self.start_h.setFixedWidth(80)
        self.start_h.setAlignment(Qt.AlignCenter)

        self.start_m = QSpinBox()
        self.start_m.setRange(0, 59)
        self.start_m.setFixedWidth(80)
        self.start_m.setAlignment(Qt.AlignCenter)

        self.start_s = QSpinBox()
        self.start_s.setRange(0, 59)
        self.start_s.setFixedWidth(80)
        self.start_s.setAlignment(Qt.AlignCenter)

        self.start_ms = QSpinBox()
        self.start_ms.setRange(0, 999)
        self.start_ms.setFixedWidth(90)
        self.start_ms.setAlignment(Qt.AlignCenter)

        spins_layout.addWidget(self.start_h)
        spins_layout.addWidget(self.start_m)
        spins_layout.addWidget(self.start_s)
        spins_layout.addWidget(self.start_ms)
        spins_layout.addStretch()
        start_layout.addLayout(spins_layout)

        start_group.setLayout(start_layout)
        layout.addWidget(start_group)

        # End time group (identical structure)
        end_group = QGroupBox("End Time")
        end_layout = QVBoxLayout()

        # Labels row for end time
        labels_layout_end = QHBoxLayout()
        lbl_h_end = QLabel("HH")
        lbl_h_end.setFixedWidth(80)
        lbl_h_end.setAlignment(Qt.AlignCenter)
        labels_layout_end.addWidget(lbl_h_end)

        lbl_m_end = QLabel("mm")
        lbl_m_end.setFixedWidth(80)
        lbl_m_end.setAlignment(Qt.AlignCenter)
        labels_layout_end.addWidget(lbl_m_end)

        lbl_s_end = QLabel("ss")
        lbl_s_end.setFixedWidth(80)
        lbl_s_end.setAlignment(Qt.AlignCenter)
        labels_layout_end.addWidget(lbl_s_end)

        lbl_ms_end = QLabel("SSS")
        lbl_ms_end.setFixedWidth(90)
        lbl_ms_end.setAlignment(Qt.AlignCenter)
        labels_layout_end.addWidget(lbl_ms_end)

        labels_layout_end.addStretch()
        end_layout.addLayout(labels_layout_end)

        # Spin boxes row for end time
        spins_layout_end = QHBoxLayout()
        self.end_h = QSpinBox()
        self.end_h.setRange(0, 99)
        self.end_h.setFixedWidth(80)
        self.end_h.setAlignment(Qt.AlignCenter)

        self.end_m = QSpinBox()
        self.end_m.setRange(0, 59)
        self.end_m.setFixedWidth(80)
        self.end_m.setAlignment(Qt.AlignCenter)

        self.end_s = QSpinBox()
        self.end_s.setRange(0, 59)
        self.end_s.setFixedWidth(80)
        self.end_s.setAlignment(Qt.AlignCenter)

        self.end_ms = QSpinBox()
        self.end_ms.setRange(0, 999)
        self.end_ms.setFixedWidth(90)
        self.end_ms.setAlignment(Qt.AlignCenter)

        spins_layout_end.addWidget(self.end_h)
        spins_layout_end.addWidget(self.end_m)
        spins_layout_end.addWidget(self.end_s)
        spins_layout_end.addWidget(self.end_ms)
        spins_layout_end.addStretch()
        end_layout.addLayout(spins_layout_end)

        end_group.setLayout(end_layout)
        layout.addWidget(end_group)

        # Parse existing times to populate spin boxes
        self.parse_time(self.start_time, self.start_h, self.start_m, self.start_s, self.start_ms)
        self.parse_time(self.end_time, self.end_h, self.end_m, self.end_s, self.end_ms)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initial enable state
        self.on_enable_toggled(self.enable_check.isChecked())

    def parse_time(self, time_str, h_spin, m_spin, s_spin, ms_spin):
        """Parse a time string like HH:MM:SS,mmm and set spin boxes."""
        if not time_str:
            return
        match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_str)
        if match:
            h_spin.setValue(int(match.group(1)))
            m_spin.setValue(int(match.group(2)))
            s_spin.setValue(int(match.group(3)))
            ms_spin.setValue(int(match.group(4)))

    def on_enable_toggled(self, checked):
        """Enable/disable all spin boxes based on checkbox."""
        for spin in [self.start_h, self.start_m, self.start_s, self.start_ms,
                     self.end_h, self.end_m, self.end_s, self.end_ms]:
            spin.setEnabled(checked)

    def get_times(self):
        """Return formatted start and end time strings, or empty strings if disabled."""
        if not self.enable_check.isChecked():
            return "", ""
        start = f"{self.start_h.value():02d}:{self.start_m.value():02d}:{self.start_s.value():02d},{self.start_ms.value():03d}"
        end = f"{self.end_h.value():02d}:{self.end_m.value():02d}:{self.end_s.value():02d},{self.end_ms.value():03d}"
        return start, end
    
class InsertPausesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Insert Pause Symbols for Gaps")
        self.setGeometry(300, 300, 500, 300)

        layout = QVBoxLayout(self)

        # Convention
        form_layout = QFormLayout()
        self.convention_combo = QComboBox()
        self.convention_combo.addItems(["GAT2", "Dresing & Pehl", "TiQ"])
        form_layout.addRow("Transcription convention:", self.convention_combo)

        # Measured pauses
        self.measured_check = QCheckBox("Use measured pauses for gaps longer than")
        self.measured_spin = QSpinBox()
        self.measured_spin.setRange(1, 60)
        self.measured_spin.setValue(2)
        self.measured_spin.setSuffix(" seconds")
        self.measured_check.toggled.connect(self.measured_spin.setEnabled)
        self.measured_spin.setEnabled(False)

        measured_layout = QHBoxLayout()
        measured_layout.addWidget(self.measured_check)
        measured_layout.addWidget(self.measured_spin)
        measured_layout.addStretch()
        form_layout.addRow(measured_layout)

        # Minimum gap
        self.min_gap_spin = QDoubleSpinBox()
        self.min_gap_spin.setRange(0.0, 10.0)
        self.min_gap_spin.setSingleStep(0.1)
        self.min_gap_spin.setValue(0.1)
        self.min_gap_spin.setSuffix(" seconds")
        form_layout.addRow("Minimum gap to consider:", self.min_gap_spin)

        # Insert mode
        mode_group = QGroupBox("Insert pauses")
        mode_layout = QVBoxLayout()

        self.separate_radio = QRadioButton("On separate lines")
        self.attach_radio = QRadioButton("At the beginning of the following segment")
        self.threshold_radio = QRadioButton("Separately if gap ≥")
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.1, 60.0)
        self.threshold_spin.setValue(4.0)
        self.threshold_spin.setSuffix(" seconds")
        self.threshold_radio.toggled.connect(self.threshold_spin.setEnabled)
        self.threshold_spin.setEnabled(False)

        self.separate_radio.setChecked(True)

        mode_layout.addWidget(self.separate_radio)
        mode_layout.addWidget(self.attach_radio)
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self.threshold_radio)
        threshold_row.addWidget(self.threshold_spin)
        threshold_row.addStretch()
        mode_layout.addLayout(threshold_row)

        mode_group.setLayout(mode_layout)
        form_layout.addRow(mode_group)

        layout.addLayout(form_layout)

        # Info label
        info = QLabel("Pauses will be inserted between existing segments based on gaps in timestamps.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(info)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_settings(self):
        if self.separate_radio.isChecked():
            mode = "separate"
            threshold = 0
        elif self.attach_radio.isChecked():
            mode = "attach"
            threshold = 0
        else:
            mode = "threshold"
            threshold = self.threshold_spin.value()

        return {
            'convention': self.convention_combo.currentText().lower().replace(' & ', '_'),
            'use_measured': self.measured_check.isChecked(),
            'measured_threshold': self.measured_spin.value(),
            'min_gap': self.min_gap_spin.value(),
            'mode': mode,
            'threshold': threshold
        }

class SymbolCategory:
    def __init__(self, name, symbols, descriptions=None):
        self.name = name
        self.symbols = symbols
        self.descriptions = descriptions or [""] * len(symbols)
        self.selected_index = 0

class AddCustomSymbolDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Symbol")
        self.setGeometry(300, 300, 500, 250)

        # Detect dark theme through parent chain
        dark = False
        try:
            if parent and hasattr(parent, '_is_dark') and parent._is_dark():
                dark = True
            elif parent and hasattr(parent, 'parent'):
                gp = parent.parent()
                if gp and hasattr(gp, 'current_theme') and gp.current_theme == "dark":
                    dark = True
        except AttributeError:
            pass

        if dark:
            self.setStyleSheet("""
                QDialog {
                    background-color: #2d2d2d;
                }
                QLabel {
                    color: #cccccc;
                }
                QLineEdit {
                    background-color: #3a3a3a;
                    color: #cccccc;
                    border: 1px solid #555;
                }
                QComboBox {
                    background-color: #3a3a3a;
                    color: #cccccc;
                    border: 1px solid #555;
                }
            """)

        layout = QVBoxLayout(self)

        # Symbol type selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Symbol type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Simple", "Segment Wrapper", "Comment Wrapper", "Comment with Scope"])
        self.type_combo.currentTextChanged.connect(self.update_fields)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        # Stacked widget for different input fields
        self.stacked = QStackedWidget()
        layout.addWidget(self.stacked)

        # ---- Page 0: Simple ----
        simple_page = QWidget()
        simple_layout = QVBoxLayout(simple_page)
        self.simple_symbol_edit = QLineEdit()
        self.simple_symbol_edit.setPlaceholderText("Enter symbol text")
        simple_layout.addWidget(QLabel("Symbol:"))
        simple_layout.addWidget(self.simple_symbol_edit)
        self.simple_desc_edit = QLineEdit()
        self.simple_desc_edit.setPlaceholderText("Optional description")
        simple_layout.addWidget(QLabel("Description (optional):"))
        simple_layout.addWidget(self.simple_desc_edit)
        self.stacked.addWidget(simple_page)

        # ---- Page 1: Segment Wrapper ----
        wrapper_page = QWidget()
        wrapper_layout = QVBoxLayout(wrapper_page)
        self.wrapper_left_edit = QLineEdit()
        self.wrapper_left_edit.setPlaceholderText("e.g., <<")
        wrapper_layout.addWidget(QLabel("Left side:"))
        wrapper_layout.addWidget(self.wrapper_left_edit)
        self.wrapper_right_edit = QLineEdit()
        self.wrapper_right_edit.setPlaceholderText("e.g., >>")
        wrapper_layout.addWidget(QLabel("Right side:"))
        wrapper_layout.addWidget(self.wrapper_right_edit)
        self.wrapper_desc_edit = QLineEdit()
        self.wrapper_desc_edit.setPlaceholderText("Optional description")
        wrapper_layout.addWidget(QLabel("Description (optional):"))
        wrapper_layout.addWidget(self.wrapper_desc_edit)
        self.stacked.addWidget(wrapper_page)

        # ---- Page 2: Comment Wrapper ----
        comment_page = QWidget()
        comment_layout = QVBoxLayout(comment_page)
        self.comment_left_edit = QLineEdit()
        self.comment_left_edit.setPlaceholderText("e.g., ((")
        comment_layout.addWidget(QLabel("Left side:"))
        comment_layout.addWidget(self.comment_left_edit)
        self.comment_right_edit = QLineEdit()
        self.comment_right_edit.setPlaceholderText("e.g., ))")
        comment_layout.addWidget(QLabel("Right side:"))
        comment_layout.addWidget(self.comment_right_edit)
        self.comment_desc_edit = QLineEdit()
        self.comment_desc_edit.setPlaceholderText("Optional description")
        comment_layout.addWidget(QLabel("Description (optional):"))
        comment_layout.addWidget(self.comment_desc_edit)
        self.stacked.addWidget(comment_page)

        # ---- Page 3: Comment with Scope ----
        reach_page = QWidget()
        reach_layout = QVBoxLayout(reach_page)
        self.reach_left_edit = QLineEdit()
        self.reach_left_edit.setPlaceholderText("e.g., <<")
        reach_layout.addWidget(QLabel("Action/comment left side:"))
        reach_layout.addWidget(self.reach_left_edit)
        self.reach_right_action_edit = QLineEdit()
        self.reach_right_action_edit.setPlaceholderText("e.g., >")
        reach_layout.addWidget(QLabel("Action/comment right side:"))
        reach_layout.addWidget(self.reach_right_action_edit)
        self.reach_right_segment_edit = QLineEdit()
        self.reach_right_segment_edit.setPlaceholderText("e.g., >")
        reach_layout.addWidget(QLabel("Segment right side:"))
        reach_layout.addWidget(self.reach_right_segment_edit)
        self.reach_desc_edit = QLineEdit()
        self.reach_desc_edit.setPlaceholderText("Optional description")
        reach_layout.addWidget(QLabel("Description (optional):"))
        reach_layout.addWidget(self.reach_desc_edit)
        self.stacked.addWidget(reach_page)

        # OK / Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.update_fields()

    def update_fields(self):
        """Switch stacked page based on selected type"""
        index = self.type_combo.currentIndex()
        self.stacked.setCurrentIndex(index)

    def get_symbol_data(self):
        """Return dictionary with symbol info, or None if validation fails"""
        data = {}
        index = self.type_combo.currentIndex()
        if index == 0:  # Simple
            symbol = self.simple_symbol_edit.text().strip()
            if not symbol:
                QMessageBox.warning(self, "Missing Data", "Symbol text cannot be empty.")
                return None
            data = {
                'type': 'simple',
                'display': symbol,
                'value': symbol,
                'description': self.simple_desc_edit.text().strip() or symbol
            }
        elif index == 1:  # Segment Wrapper
            left = self.wrapper_left_edit.text().strip()
            right = self.wrapper_right_edit.text().strip()
            if not left or not right:
                QMessageBox.warning(self, "Missing Data", "Both left and right sides are required.")
                return None
            display = f"{left}text{right}"
            data = {
                'type': 'wrapper',
                'display': display,
                'left': left,
                'right': right,
                'description': self.wrapper_desc_edit.text().strip() or display
            }
        elif index == 2:  # Comment Wrapper
            left = self.comment_left_edit.text().strip()
            right = self.comment_right_edit.text().strip()
            if not left or not right:
                QMessageBox.warning(self, "Missing Data", "Both left and right sides are required.")
                return None
            display = f"{left}comment{right}"
            data = {
                'type': 'comment',
                'display': display,
                'left': left,
                'right': right,
                'description': self.comment_desc_edit.text().strip() or display
            }
        else:  # Comment with Scope
            left = self.reach_left_edit.text().strip()
            right_action = self.reach_right_action_edit.text().strip()
            right_segment = self.reach_right_segment_edit.text().strip()
            if not left or not right_action or not right_segment:
                QMessageBox.warning(self, "Missing Data", "All three sides are required.")
                return None
            display = f"{left}comment{right_action}text{right_segment}"
            data = {
                'type': 'comment_reach',
                'display': display,
                'left': left,
                'right': right_action,
                'segment_right': right_segment,
                'description': self.reach_desc_edit.text().strip() or display
            }
        return data

class EnhancedSymbolDialog(QDialog):
    custom_symbols_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_symbols.json")
    custom_symbols = []

    def __init__(self, parent=None, initial_category=None):
        super().__init__(parent)
        # NOTE: do NOT store the editor as `self.parent` — that shadows
        # QWidget.parent() and crashes callers like AddCustomSymbolDialog
        # (TypeError: '<Editor>' object is not callable).
        self.editor = parent
        self.initial_category = initial_category
        self.categories = []
        self.current_category_index = 0
        self.selected_option = 0
        self.load_custom_symbols()
        self.init_categories()
        self.init_ui()

    def _is_dark(self):
        """Detect if the parent editor is in dark theme."""
        try:
            return self.editor.current_theme == "dark"
        except AttributeError:
            return False

    def init_categories(self):
        # GAT2
        self.categories.append(SymbolCategory(
            "GAT2",
            ["(.)", "(-)", "(--)", "(---)", "(_._)", "(())", "<<>>", "[ ]",
             "°h", "°hh", "°hhh", "h°", "hh°", "hhh°"],
            ["micropause", "short estimated pause", "medium estimated pause", "long estimated pause",
             "measured pause", "comment", "action/comment with scope", "overlap",
             "short inhale", "medium inhale", "long inhale",
             "short exhale", "medium exhale", "long exhale"]
        ))
        # Dresing & Pehl
        self.categories.append(SymbolCategory(
            "Dresing && Pehl",
            ["(.)", "(..)", "(...)", "(_)", "//", "(   )", "⏱️"],
            ["short estimated pause", "medium estimated pause", "long estimated pause",
             "measured pause", "overlap", "comment", "insert timestamp"]
        ))
        # TiQ
        self.categories.append(SymbolCategory(
            "TiQ",
            ["(.)", "(_)", "(())", "└", "@(.)@", "@(_)@", "@(   )@", "°   °", "//   //"],
            ["short pause", "measured pause", "comment",
             "overlap marker", "short laughter", "laughing seconds",
             "laughing speech", "quiet speech", "listener's signal"]
        ))
        # Custom
        custom_symbols_list = [s['display'] for s in self.custom_symbols]
        custom_descriptions = [s.get('description', s['type']) for s in self.custom_symbols]
        self.categories.append(SymbolCategory(
            "Custom",
            custom_symbols_list,
            custom_descriptions
        ))

    def load_custom_symbols(self):
        try:
            if os.path.exists(EnhancedSymbolDialog.custom_symbols_file):
                with open(EnhancedSymbolDialog.custom_symbols_file, 'r', encoding='utf-8') as f:
                    self.custom_symbols = json.load(f)
            else:
                self.custom_symbols = []
        except Exception as e:
            logger.error(f"Failed to load custom symbols: {e}")
            self.custom_symbols = []

    def save_custom_symbols(self):
        try:
            with open(EnhancedSymbolDialog.custom_symbols_file, 'w', encoding='utf-8') as f:
                json.dump(self.custom_symbols, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save custom symbols: {e}")
            QMessageBox.warning(self, "Error", f"Could not save custom symbols: {e}")

    def init_ui(self):
        self.setWindowTitle("Insert Symbol")
        self.setGeometry(300, 300, 650, 500)

        if self._is_dark():
            self.setStyleSheet("""
                QDialog {
                    background-color: #2d2d2d;
                }
                QLabel {
                    color: #cccccc;
                }
            """)

        layout = QVBoxLayout(self)

        # Category tabs
        tab_layout = QHBoxLayout()
        self.category_buttons = []
        for i, category in enumerate(self.categories):
            btn = QPushButton(category.name)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setFocusPolicy(Qt.TabFocus)
            if self._is_dark():
                btn.setStyleSheet("""
                    QPushButton {
                        padding: 8px 15px;
                        font-weight: bold;
                        border: 2px solid #555;
                        border-radius: 5px 5px 0 0;
                        background-color: #3a3a3a;
                        color: #cccccc;
                    }
                    QPushButton:checked {
                        background-color: #4a90e2;
                        color: white;
                        border-bottom-color: #4a90e2;
                    }
                    QPushButton:hover:!checked {
                        background-color: #4a4a4a;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        padding: 8px 15px;
                        font-weight: bold;
                        border: 2px solid #ccc;
                        border-radius: 5px 5px 0 0;
                        background-color: #f0f0f0;
                    }
                    QPushButton:checked {
                        background-color: #4a90e2;
                        color: white;
                        border-bottom-color: #4a90e2;
                    }
                    QPushButton:hover:!checked {
                        background-color: #e0e0e0;
                    }
                """)
            btn.clicked.connect(lambda checked, idx=i: self.switch_category(idx))
            tab_layout.addWidget(btn)
            self.category_buttons.append(btn)

        tab_instruction = QLabel("<i>(Tab to switch)</i>")
        tab_instruction.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if self._is_dark():
            tab_instruction.setStyleSheet("color: #888; font-size: 11px;")
        else:
            tab_instruction.setStyleSheet("color: #555; font-size: 11px;")
        tab_layout.addWidget(tab_instruction)
        tab_layout.addSpacing(23)
        layout.addLayout(tab_layout)
        
        # Management buttons for custom category
        self.management_layout = QHBoxLayout()
               
        self.btn_add_symbol = QPushButton("Add New Symbol")
        self.btn_add_symbol.clicked.connect(self.add_new_symbol)
        self.btn_add_symbol.setVisible(False)
        
        self.btn_delete_custom = QPushButton("Delete Selected")
        self.btn_delete_custom.clicked.connect(self.delete_selected_symbol)
        self.btn_delete_custom.setVisible(False)
        self.btn_delete_custom.setStyleSheet("""
            QPushButton:hover {
                background-color: #fdd2d2;
                border: 1px solid #cc0000;
                border-radius: 3px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                border-color: #999999;
                color: #666666;
            }
        """)

        self.btn_export_custom = QPushButton("Export")
        self.btn_export_custom.clicked.connect(self.export_custom_symbols)
        self.btn_export_custom.setVisible(False)

        self.btn_import_custom = QPushButton("Import")
        self.btn_import_custom.clicked.connect(self.import_custom_symbols)
        self.btn_import_custom.setVisible(False)

        self.management_layout.addWidget(self.btn_add_symbol)
        self.management_layout.addWidget(self.btn_delete_custom)
        self.management_layout.addStretch()
        self.management_layout.addWidget(self.btn_export_custom)
        self.management_layout.addWidget(self.btn_import_custom)

        layout.addLayout(self.management_layout)

        # Scrollable grid area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.category_widget = QWidget()
        self.category_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.category_layout = QGridLayout(self.category_widget)
        self.category_layout.setSpacing(10)
        self.category_layout.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidget(self.category_widget)
        layout.addWidget(self.scroll_area)

        # Selected description label
        self.selected_label = QLabel("")
        self.selected_label.setAlignment(Qt.AlignCenter)
        if self._is_dark():
            self.selected_label.setStyleSheet("""
                QLabel {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 6px;
                    font-size: 12px;
                    color: #cccccc;
                    margin-top: 5px;
                    margin-bottom: 5px;
                }
            """)
        else:
            self.selected_label.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 6px;
                    font-size: 12px;
                    color: #333;
                    margin-top: 5px;
                    margin-bottom: 5px;
                }
            """)
        layout.addWidget(self.selected_label)

        # OK / Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Shortcuts for Tab / Shift+Tab to switch categories
        self.tab_shortcut = QShortcut(QKeySequence(Qt.Key_Tab), self)
        self.tab_shortcut.activated.connect(self.next_category)
        self.shift_tab_shortcut = QShortcut(QKeySequence(Qt.Key_Backtab), self)
        self.shift_tab_shortcut.activated.connect(self.prev_category)
        self.tab_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.shift_tab_shortcut.setContext(Qt.WidgetWithChildrenShortcut)

        self.update_category_display()
        if self.initial_category is not None:
            self.switch_category(self.initial_category)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

    def next_category(self):
        new_index = (self.current_category_index + 1) % len(self.categories)
        self.switch_category(new_index)

    def prev_category(self):
        new_index = (self.current_category_index - 1) % len(self.categories)
        self.switch_category(new_index)

    def switch_category(self, index):
        if 0 <= index < len(self.categories):
            for i, btn in enumerate(self.category_buttons):
                btn.setChecked(i == index)

            self.current_category_index = index
            self.selected_option = 0
            self.categories[index].selected_index = 0
            self.update_category_display()
            self.setFocus()

            # Show/hide custom management buttons
            is_custom = (index == len(self.categories) - 1)
            self.btn_add_symbol.setVisible(is_custom)
            self.btn_export_custom.setVisible(is_custom)
            self.btn_import_custom.setVisible(is_custom)
            self.btn_delete_custom.setVisible(is_custom)

    def update_category_display(self):
        # Clear all widgets from the grid layout
        for i in reversed(range(self.category_layout.count())):
            widget = self.category_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        category = self.categories[self.current_category_index]

        self.symbol_labels = []
        for i, (symbol, desc) in enumerate(zip(category.symbols, category.descriptions)):
            escaped_symbol = (symbol.replace('&', '&amp;')
                                   .replace('<', '&lt;')
                                   .replace('>', '&gt;'))

            label = QLabel(f"<b>{escaped_symbol}</b>")
            label.setAlignment(Qt.AlignCenter)
            label.setToolTip(desc)
            label.setCursor(Qt.PointingHandCursor)
            label.setFocusPolicy(Qt.ClickFocus)

            # Set size limits
            label.setMinimumSize(110, 60)
            label.setMaximumSize(180, 100)
            label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

            if i == self.selected_option:
                if self._is_dark():
                    label.setStyleSheet("""
                        QLabel {
                            border: 3px solid #ff6600;
                            border-radius: 8px;
                            padding: 15px;
                            background-color: #554433;
                            font-size: 14px;
                            color: #ffffff;
                        }
                    """)
                else:
                    label.setStyleSheet("""
                        QLabel {
                            border: 3px solid #ff6600;
                            border-radius: 8px;
                            padding: 15px;
                            background-color: #fff0cc;
                            font-size: 14px;
                        }
                    """)
            else:
                if self._is_dark():
                    label.setStyleSheet("""
                        QLabel {
                            border: 2px solid #555;
                            border-radius: 8px;
                            padding: 15px;
                            background-color: #3a3a3a;
                            font-size: 14px;
                            color: #cccccc;
                        }
                        QLabel:hover {
                            background-color: #4a4a4a;
                            border-color: #888;
                        }
                    """)
                else:
                    label.setStyleSheet("""
                        QLabel {
                            border: 2px solid #ccc;
                            border-radius: 8px;
                            padding: 15px;
                            background-color: #f9f9f9;
                            font-size: 14px;
                        }
                        QLabel:hover {
                            background-color: #e0e0e0;
                            border-color: #999;
                        }
                    """)

            label.mousePressEvent = lambda event, idx=i: self.symbol_clicked(idx)

            self.category_layout.addWidget(label, i // 4, i % 4)
            self.symbol_labels.append(label)

        # Ensure the selected symbol is visible
        if self.symbol_labels:
            self.scroll_area.ensureWidgetVisible(self.symbol_labels[self.selected_option])

        # Update description label
        desc = category.descriptions[self.selected_option] if category.descriptions else ""
        self.selected_label.setText(desc)

    def symbol_clicked(self, index):
        self.selected_option = index
        self.categories[self.current_category_index].selected_index = index
        self.update_category_display()

    def keyPressEvent(self, event):
        # Arrow keys always navigate the grid (dialog has focus)
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                           Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            cols = 4
            current_idx = self.selected_option
            max_idx = len(self.categories[self.current_category_index].symbols) - 1

            if event.key() == Qt.Key_Left:
                new_idx = max(0, current_idx - 1)
                self.symbol_clicked(new_idx)
                event.accept()
            elif event.key() == Qt.Key_Right:
                new_idx = min(max_idx, current_idx + 1)
                self.symbol_clicked(new_idx)
                event.accept()
            elif event.key() == Qt.Key_Up:
                new_idx = max(0, current_idx - cols)
                self.symbol_clicked(new_idx)
                event.accept()
            elif event.key() == Qt.Key_Down:
                new_idx = min(max_idx, current_idx + cols)
                self.symbol_clicked(new_idx)
                event.accept()
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.accept()
                event.accept()
            elif event.key() == Qt.Key_Escape:
                self.reject()
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def add_new_symbol(self):
        """Open the add custom symbol dialog and append the new symbol."""
        dialog = AddCustomSymbolDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            symbol_data = dialog.get_symbol_data()
            if symbol_data:
                self.custom_symbols.append(symbol_data)
                self.save_custom_symbols()
                self.refresh_custom_category()

    def refresh_custom_category(self):
        custom_idx = len(self.categories) - 1
        self.categories[custom_idx].symbols = [s['display'] for s in self.custom_symbols]
        self.categories[custom_idx].descriptions = [s.get('description', s['type']) for s in self.custom_symbols]
        self.categories[custom_idx].selected_index = 0

        if self.current_category_index == custom_idx:
            self.selected_option = 0
            self.update_category_display()

    def export_custom_symbols(self):
        base_dir = getattr(self.editor, '_base_dir_for_dialog', lambda: '')()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Custom Symbols", base_dir,
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.custom_symbols, f, indent=2)
                QMessageBox.information(self, "Success", f"Custom symbols exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not export: {e}")

    def import_custom_symbols(self):
        base_dir = getattr(self.editor, '_base_dir_for_dialog', lambda: '')()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Custom Symbols", base_dir,
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
                        self.custom_symbols.extend(imported)
                    elif reply == QMessageBox.No:
                        self.custom_symbols = imported
                    else:
                        return

                    self.save_custom_symbols()
                    self.refresh_custom_category()
                    QMessageBox.information(self, "Success", f"Imported {len(imported)} symbols")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not import: {e}")

    def delete_selected_symbol(self):
        if self.current_category_index != len(self.categories) - 1:
            return
        if not self.custom_symbols:
            return

        reply = QMessageBox.question(
            self, "Delete Symbol",
            f"Are you sure you want to delete the symbol '{self.categories[-1].symbols[self.selected_option]}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self.custom_symbols[self.selected_option]
            self.save_custom_symbols()
            if self.selected_option >= len(self.custom_symbols):
                self.selected_option = max(0, len(self.custom_symbols) - 1)
            self.refresh_custom_category()

    def get_selected_symbol_info(self):
        category = self.categories[self.current_category_index]
        symbol_display = category.symbols[self.selected_option]

        if self.current_category_index == len(self.categories) - 1:
            symbol_data = self.custom_symbols[self.selected_option].copy()
            symbol_data['category'] = 'custom'
            return symbol_data

        return {
            'category': category.name.lower(),
            'display': symbol_display,
            'type': 'builtin',
            'index': self.selected_option
        }
    
class CommentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.comment_text = ""
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Add Comment")
        self.setGeometry(300, 300, 500, 200)

        layout = QVBoxLayout(self)
        
        instructions = QLabel("Enter your comment (will be formatted as ((comment))):")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("Enter comment here")
        layout.addWidget(self.comment_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.comment_edit.setFocus()
        
    def get_comment(self):
        return f"(({self.comment_edit.text()}))"
    
class RichEditDialog(QDialog):
    """Enhanced edit dialog with bold/italic/underline buttons and shortcuts."""
    def __init__(self, current_text, parent=None):
        super().__init__(parent)
        self.current_text = current_text
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Edit Segment Content")
        self.setGeometry(300, 300, 600, 150)

        layout = QVBoxLayout(self)

        # Toolbar with formatting buttons
        toolbar = QHBoxLayout()
        self.btn_bold = QPushButton("B")
        self.btn_bold.setToolTip("Bold (Ctrl+B)")
        self.btn_bold.setFixedSize(30, 30)
        self.btn_bold.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_bold.clicked.connect(self.insert_bold)

        self.btn_italic = QPushButton("I")
        self.btn_italic.setToolTip("Italic (Ctrl+I)")
        self.btn_italic.setFixedSize(30, 30)
        self.btn_italic.setStyleSheet("font-style: italic; font-size: 14px;")
        self.btn_italic.clicked.connect(self.insert_italic)

        self.btn_underline = QPushButton("U")
        self.btn_underline.setToolTip("Underline (Ctrl+U)")
        self.btn_underline.setFixedSize(30, 30)
        self.btn_underline.setStyleSheet("text-decoration: underline; font-size: 14px;")
        self.btn_underline.clicked.connect(self.insert_underline)

        toolbar.addWidget(self.btn_bold)
        toolbar.addWidget(self.btn_italic)
        toolbar.addWidget(self.btn_underline)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Single‑line text edit
        self.text_edit = QLineEdit()
        self.text_edit.setText(self.current_text)
        self.text_edit.setStyleSheet("""
            QLineEdit {
                font-family: monospace;
                font-size: 14px;
                padding: 8px;
                background-color: palette(base);
                color: palette(text);
                border: 2px solid palette(mid);
                border-radius: 5px;
            }
            QLineEdit:focus {
                border: 2px solid #4a90e2;
            }
        """)
        self.text_edit.returnPressed.connect(self.accept)
        layout.addWidget(self.text_edit)

        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Shortcuts
        self.shortcut_bold = QShortcut(QKeySequence("Ctrl+B"), self)
        self.shortcut_bold.activated.connect(self.insert_bold)
        self.shortcut_italic = QShortcut(QKeySequence("Ctrl+I"), self)
        self.shortcut_italic.activated.connect(self.insert_italic)
        self.shortcut_underline = QShortcut(QKeySequence("Ctrl+U"), self)
        self.shortcut_underline.activated.connect(self.insert_underline)

        self.text_edit.setFocus()
        self.text_edit.selectAll()

    def insert_format(self, start_marker, end_marker):
        """Wrap selected text with markers."""
        cursor_pos = self.text_edit.cursorPosition()
        selected_text = self.text_edit.selectedText()
        if selected_text:
            new_text = self.text_edit.text()[:self.text_edit.selectionStart()] + \
                       start_marker + selected_text + end_marker + \
                       self.text_edit.text()[self.text_edit.selectionEnd():]
            self.text_edit.setText(new_text)
            # Restore selection around the just‑wrapped text
            new_start = self.text_edit.selectionStart()
            self.text_edit.setSelection(new_start, len(selected_text))
        else:
            # Insert markers and place cursor between them
            text = self.text_edit.text()
            new_text = text[:cursor_pos] + start_marker + end_marker + text[cursor_pos:]
            self.text_edit.setText(new_text)
            self.text_edit.setCursorPosition(cursor_pos + len(start_marker))

    def insert_bold(self):
        self.insert_format("#@B", "#@/B")

    def insert_italic(self):
        self.insert_format("#@I", "#@/I")

    def insert_underline(self):
        self.insert_format("#@U", "#@/U")

    def get_text(self):
        return self.text_edit.text()

class SettingsDialog(QDialog):
    def __init__(self, current_font, current_theme, cjk_mode, base_directory, parent=None):
        super().__init__(parent)
        self.selected_font = current_font
        self.current_theme = current_theme
        self.cjk_mode = cjk_mode
        self.base_directory = base_directory  # '' means system default
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Settings")
        self.setGeometry(100, 100, 500, 360)
        
        layout = QVBoxLayout(self)
        
        # ── GUI Settings ─────────────────────────────────────────
        gui_group = QGroupBox("GUI Settings")
        gui_layout = QVBoxLayout(gui_group)
        
        theme_row = QHBoxLayout()
        self.theme_toggle = ThemeToggle(dark=(self.current_theme == "dark"))
        theme_row.addWidget(self.theme_toggle)
        theme_row.addStretch()
        gui_layout.addLayout(theme_row)
        
        gui_layout.addWidget(QLabel("Default path:"))
        self.base_system_radio = QRadioButton("System default")
        self.base_system_radio.setChecked(not self.base_directory)
        gui_layout.addWidget(self.base_system_radio)

        custom_row = QHBoxLayout()
        self.base_custom_radio = QRadioButton("Custom path:")
        self.base_custom_radio.setChecked(bool(self.base_directory))
        self.base_path_input = QLineEdit()
        self.base_path_input.setReadOnly(True)
        self.base_path_input.setPlaceholderText("System default")
        self.browse_btn = QPushButton("Browse\u2026")
        self.browse_btn.clicked.connect(self.select_base_dir)
        self._update_base_path_display()
        self.base_system_radio.toggled.connect(self._on_base_radio_toggled)
        self.base_custom_radio.toggled.connect(self._on_base_radio_toggled)
        custom_row.addWidget(self.base_custom_radio)
        custom_row.addWidget(self.base_path_input)
        custom_row.addWidget(self.browse_btn)
        custom_row.addStretch()
        gui_layout.addLayout(custom_row)

        layout.addWidget(gui_group)
        
        # ── Project Settings ─────────────────────────────────────
        project_group = QGroupBox("Project Settings")
        project_layout = QVBoxLayout(project_group)
        
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Text Display Font:"))
        self.font_button = QPushButton(f"{self.selected_font.family()} {self.selected_font.pointSize()}pt")
        self.font_button.clicked.connect(self.select_font)
        font_layout.addWidget(self.font_button)
        font_layout.addStretch()
        project_layout.addLayout(font_layout)
        
        self.cjk_checkbox = QCheckBox("Optimize for CJK (double spaces for overlap indentation)")
        self.cjk_checkbox.setChecked(self.cjk_mode)
        project_layout.addWidget(self.cjk_checkbox)

        layout.addWidget(project_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def select_font(self):
        font, ok = QFontDialog.getFont(self.selected_font, self)
        if ok:
            self.selected_font = font
            self.font_button.setText(f"{font.family()} {font.pointSize()}pt")
    
    def get_font(self):
        return self.selected_font
    
    def get_theme(self):
        return "dark" if self.theme_toggle.is_dark() else "light"
    
    def get_cjk_mode(self):
        return self.cjk_checkbox.isChecked()
    
    def _update_base_path_display(self):
        if self.base_custom_radio.isChecked() and self.base_directory:
            self.base_path_input.setText(self.base_directory)
        else:
            self.base_path_input.clear()
        self.base_path_input.setEnabled(self.base_custom_radio.isChecked())
        self.browse_btn.setEnabled(self.base_custom_radio.isChecked())

    def _on_base_radio_toggled(self):
        self._update_base_path_display()

    def select_base_dir(self):
        start_dir = self.base_directory if self.base_directory else ""
        directory = QFileDialog.getExistingDirectory(
            self, "Choose Default Path", start_dir
        )
        if directory:
            self.base_directory = directory
            self.base_path_input.setText(directory)
    
    def get_base_directory(self):
        if self.base_system_radio.isChecked():
            return ""
        return self.base_directory

class ProjectMemoDialog(QDialog):
    def __init__(self, project_name="", project_memo="", parent=None):
        super().__init__(parent)
        self.project_name = project_name
        self.project_memo = project_memo
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Project Memo")
        self.setGeometry(300, 300, 500, 400)
        
        layout = QVBoxLayout(self)
        
        # Project name
        layout.addWidget(QLabel("Project Name:"))
        self.name_edit = QLineEdit(self.project_name)
        self.name_edit.setPlaceholderText("Enter project name")
        layout.addWidget(self.name_edit)
        
        # Project memo
        layout.addWidget(QLabel("Project Memo:"))
        self.memo_edit = QPlainTextEdit()
        self.memo_edit.setPlainText(self.project_memo)
        self.memo_edit.setPlaceholderText("Enter project notes or description")
        layout.addWidget(self.memo_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def get_project_info(self):
        return {
            'name': self.name_edit.text(),
            'memo': self.memo_edit.toPlainText()
        }

class JsonImportDialog(QDialog):
    def __init__(self, has_tokens=False, parent=None):
        super().__init__(parent)
        self.import_option = "one_block"  # one_block, tokens, auto_segment
        self.has_tokens = has_tokens
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("JSON Import Options")
        self.setGeometry(300, 300, 500, 250)
        
        layout = QVBoxLayout(self)
        
        instructions = QLabel("How would you like to import this JSON file?")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        self.one_block_radio = QRadioButton("Import as one continuous block")
        self.one_block_radio.setChecked(True)
        layout.addWidget(self.one_block_radio)
        
        if self.has_tokens:
            self.tokens_radio = QRadioButton("Import each token as separate block")
            layout.addWidget(self.tokens_radio)
            
            self.auto_radio = QRadioButton("Auto-segment based on pause detection")
            layout.addWidget(self.auto_radio)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def get_import_option(self):
        if self.has_tokens:
            if self.one_block_radio.isChecked():
                return "one_block"
            elif self.tokens_radio.isChecked():
                return "tokens"
            else:
                return "auto_segment"
        else:
            return "one_block"

class UnassignedSegmentsDialog(QDialog):
    def __init__(self, unassigned_count, parent=None):
        super().__init__(parent)
        self.unassigned_count = unassigned_count
        self.selected_option = "skip"  # skip, no_label, unknown
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Unassigned Segments")
        self.setGeometry(300, 300, 450, 200)
        
        layout = QVBoxLayout(self)
        
        instructions = QLabel(f"Found {self.unassigned_count} unassigned segment(s). How should they be handled?")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        # Radio buttons for options
        self.skip_radio = QRadioButton("Do not include in SRT file")
        self.skip_radio.setChecked(True)
        layout.addWidget(self.skip_radio)
        
        self.no_label_radio = QRadioButton("Include without speaker label")
        layout.addWidget(self.no_label_radio)
        
        self.unknown_radio = QRadioButton("Label as 'Unknown:'")
        layout.addWidget(self.unknown_radio)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def get_selected_option(self):
        if self.skip_radio.isChecked():
            return "skip"
        elif self.no_label_radio.isChecked():
            return "no_label"
        else:
            return "unknown"

class ExportPreviewDialog(QDialog):
    # Class-level settings cache: persists across dialog instances within a GUI session
    _last_settings = None

    def __init__(self, parent=None, has_timestamps=True,
                 timestamp_style="curly", custom_pattern="{HH:mm:ss}",
                 project_info=None, audio_path=None):
        super().__init__(parent)
        self.main_window = parent
        self.include_timestamps = has_timestamps
        self.current_include_timestamps = has_timestamps
        self.export_format = "html"
        self.transcript_convention = "gat2"
        self.project_info = project_info or {}
        self.audio_path = audio_path
        self.timestamp_style = timestamp_style
        self.custom_timestamp_pattern = custom_pattern
        self.init_ui()
        # Restore last session's settings if available
        self._restore_last_settings()

    def accept(self):
        """Save current settings before closing so they persist for next export."""
        ExportPreviewDialog._last_settings = self.get_export_settings()
        super().accept()

    def _restore_last_settings(self):
        """Apply previously saved settings to the dialog widgets."""
        settings = ExportPreviewDialog._last_settings
        if settings is None:
            return

        # ------ Restore format ------
        fmt = settings.get('format', 'html')
        if fmt == 'html':
            self.html_radio.setChecked(True)
        elif fmt == 'docx':
            self.docx_radio.setChecked(True)
        elif fmt == 'txt':
            self.txt_radio.setChecked(True)
        elif fmt == 'srt':
            self.srt_radio.setChecked(True)

        # ------ Restore convention ------
        conv = settings.get('convention', 'gat2')
        if conv == 'gat2':
            self.convention_combo.setCurrentText("GAT2 (Conversation Analysis)")
        elif conv == 'dresing_pehl':
            self.convention_combo.setCurrentText("Dresing & Pehl, Kuckartz (Semantic Transcription)")
        elif conv == 'tiq':
            self.convention_combo.setCurrentText("TiQ (Talk in Qualitative Research)")

        # ------ Override defaults set by on_convention_changed ------
        if self.include_timestamps and 'include_timestamps' in settings:
            self.timestamp_check.setChecked(settings['include_timestamps'])
            self.current_include_timestamps = settings['include_timestamps']

        ts_style = settings.get('timestamp_style', '')
        if ts_style == 'curly':
            self.ts_curly_radio.setChecked(True)
        elif ts_style == 'hash':
            self.ts_hash_radio.setChecked(True)
        elif ts_style == 'bracket':
            self.ts_bracket_radio.setChecked(True)
        elif ts_style == 'custom':
            self.ts_custom_radio.setChecked(True)
            self.ts_custom_edit.setText(settings.get('custom_timestamp_pattern', ''))

        self.wrap_check.setChecked(settings.get('wrap_enabled', False))
        self.wrap_spin.setValue(settings.get('wrap_length', 60))
        self.character_wrap_check.setChecked(settings.get('character_wrap', False))

        self.title_check.setChecked(settings.get('include_title', True))
        self.memo_check.setChecked(settings.get('include_memo', True))
        self.audio_check.setChecked(settings.get('include_audio', True))

        self.concat_check.setChecked(settings.get('concatenate_turns', False))
        self.blank_line_check.setChecked(settings.get('add_blank_line', False))
        delim = settings.get('delimiter_choice', 'default')
        if delim == 'custom':
            self.delimiter_custom.setChecked(True)
            self.custom_delimiter_edit.setText(settings.get('custom_delimiter', ''))
        else:
            self.delimiter_default.setChecked(True)

        self.update_export_options_state()
        self.update_preview()

    def init_ui(self):
        self.setWindowTitle("Export Preview")
        # Fixed width, dynamic height
        fixed_width = 800
        screen = QApplication.primaryScreen()
        screen_geom = screen.availableGeometry()
        screen_height = screen_geom.height()

        # Compute initial height: 85% of screen height, but clamp to reasonable range
        init_height = int(screen_height * 0.85)
        init_height = max(500, min(900, init_height))   # between 500 and 900

        self.resize(fixed_width, init_height)
        self.setMinimumSize(600, 400)      # allow some resizing, but width can be changed
        # Optional: prevent horizontal resizing by setting maximum width
        # self.setMaximumWidth(fixed_width)   # uncomment if you want fixed width

        # Center the dialog
        self.move((screen_geom.width() - fixed_width) // 2,
                  (screen_geom.height() - init_height) // 2)

        layout = QVBoxLayout(self)

        # ----- Format selection -----
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Export Format:"))

        self.html_radio = QRadioButton("HTML (.html)")
        self.html_radio.setChecked(True)
        format_layout.addWidget(self.html_radio)

        self.docx_radio = QRadioButton("Word Document (.docx)")
        format_layout.addWidget(self.docx_radio)

        self.txt_radio = QRadioButton("Plain Text (.txt)")
        format_layout.addWidget(self.txt_radio)

        self.srt_radio = QRadioButton("Subtitle File (.srt)")
        format_layout.addWidget(self.srt_radio)
        format_layout.addStretch()

        if not self.include_timestamps:
            self.srt_radio.setEnabled(False)
            self.srt_radio.setToolTip("SRT export requires timestamp information. Original file does not contain timestamps.")

        # ----- Convention selection -----
        convention_layout = QHBoxLayout()
        convention_layout.addWidget(QLabel("Transcript Convention:"))

        self.convention_combo = QComboBox()
        self.convention_combo.addItems([
            "GAT2 (Conversation Analysis)",
            "Dresing & Pehl, Kuckartz (Semantic Transcription)",
            "TiQ (Talk in Qualitative Research)"
        ])
        convention_layout.addWidget(self.convention_combo)
        convention_layout.addStretch()

        # ---------- Create all widgets first ----------

        # Timestamp widgets
        self.timestamp_check = QCheckBox("Include timestamps")
        self.timestamp_check.setChecked(self.include_timestamps)
        self.timestamp_check.setEnabled(self.include_timestamps)

        self.ts_format_widget = QWidget()
        ts_format_layout = QHBoxLayout(self.ts_format_widget)
        ts_format_layout.setContentsMargins(0, 0, 0, 0)

        self.ts_curly_radio = QRadioButton("Curly brackets")
        self.ts_hash_radio = QRadioButton("Hashtags")
        self.ts_bracket_radio = QRadioButton("Square brackets")
        self.ts_custom_radio = QRadioButton("Custom format:")

        ts_format_layout.addWidget(self.ts_curly_radio)
        ts_format_layout.addWidget(self.ts_hash_radio)
        ts_format_layout.addWidget(self.ts_bracket_radio)
        ts_format_layout.addWidget(self.ts_custom_radio)

        self.ts_custom_edit = QLineEdit()
        self.ts_custom_edit.setPlaceholderText("e.g. <HH:mm:ss-xx>")
        self.ts_custom_edit.setEnabled(False)
        ts_format_layout.addWidget(self.ts_custom_edit)
        ts_format_layout.addStretch()

        ts_line_layout = QHBoxLayout()
        ts_line_layout.addWidget(self.timestamp_check)
        ts_line_layout.addWidget(self.ts_format_widget)
        ts_line_layout.addStretch()

        # Concatenation widgets
        self.concat_check = QCheckBox("Concatenate segments")

        self.delimiter_default = QRadioButton("Default delimiter")
        self.delimiter_custom = QRadioButton("Custom delimiter:")
        self.delimiter_default.setChecked(True)

        self.custom_delimiter_edit = QLineEdit()
        self.custom_delimiter_edit.setPlaceholderText("e.g., |")
        self.custom_delimiter_edit.setEnabled(False)

        self.delimiter_widget = QWidget()
        inner_layout = QHBoxLayout(self.delimiter_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.addWidget(self.delimiter_default)
        inner_layout.addWidget(self.delimiter_custom)
        inner_layout.addWidget(self.custom_delimiter_edit)
        inner_layout.addStretch()

        self.blank_line_check = QCheckBox("Append empty line")
        self.blank_line_check.setChecked(False)

        self.diarization_check = QCheckBox("Include diarization")
        self.diarization_check.setChecked(True)

        # Line wrapping widgets
        self.wrap_check = QCheckBox("Wrap lines at:")
        self.wrap_spin = QSpinBox()
        self.wrap_spin.setRange(30, 200)
        self.wrap_spin.setValue(60)
        self.wrap_spin.setSuffix(" characters")
        self.wrap_spin.setEnabled(False)

        self.character_wrap_check = QCheckBox("Force character‑based wrapping")
        self.character_wrap_check.setEnabled(False)

        wrap_layout = QHBoxLayout()
        wrap_layout.addWidget(self.wrap_check)
        wrap_layout.addWidget(self.wrap_spin)
        wrap_layout.addWidget(self.character_wrap_check)
        wrap_layout.addStretch()

        # Header widgets
        self.title_check = QCheckBox("Include project title")
        self.title_check.setChecked(True)
        self.memo_check = QCheckBox("Include project memo")
        self.memo_check.setChecked(True)
        self.audio_check = QCheckBox("Include audio file path")
        self.audio_check.setChecked(True)

        # Preview area and buttons
        preview_label = QLabel("Preview:")
        preview_label.setFont(QFont("Arial", 12, QFont.Bold))

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)

        # ---------- Create group boxes ----------

        # Timestamp Options group
        timestamp_group = QGroupBox("Timestamp Options")
        timestamp_layout = QVBoxLayout()
        timestamp_layout.addLayout(ts_line_layout)
        timestamp_group.setLayout(timestamp_layout)

        # Concatenation group
        concat_group = QGroupBox("Concatenation")
        concat_layout = QVBoxLayout()

        # Single row: concat_check, delimiter_widget, blank_line_check, diarization_check
        main_row = QHBoxLayout()
        main_row.addWidget(self.concat_check)
        main_row.addWidget(self.delimiter_widget)
        main_row.addWidget(self.blank_line_check)
        main_row.addWidget(self.diarization_check)
        main_row.addStretch()
        concat_layout.addLayout(main_row)

        concat_group.setLayout(concat_layout)

        # Line Wrapping group
        wrapping_group = QGroupBox("Line Wrapping")
        wrapping_layout_group = QVBoxLayout()  # avoid name conflict with earlier wrap_layout
        wrapping_layout_group.addLayout(wrap_layout)
        wrapping_group.setLayout(wrapping_layout_group)

        # Header Options group
        header_group = QGroupBox("Header Options")
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.title_check)
        header_layout.addWidget(self.memo_check)
        header_layout.addWidget(self.audio_check)
        header_layout.addStretch()
        header_group.setLayout(header_layout)

        # ---------- Assemble main layout ----------
        layout.addLayout(format_layout)
        layout.addLayout(convention_layout)
        layout.addWidget(timestamp_group)
        layout.addWidget(concat_group)
        layout.addWidget(wrapping_group)
        layout.addWidget(header_group)
        layout.addWidget(preview_label)
        layout.addWidget(self.preview_text)
        layout.addWidget(button_box)

        # ---------- Connect signals ----------
        self.html_radio.toggled.connect(self.on_format_changed)
        self.docx_radio.toggled.connect(self.on_format_changed)
        self.txt_radio.toggled.connect(self.on_format_changed)
        self.srt_radio.toggled.connect(self.on_format_changed)

        self.convention_combo.currentTextChanged.connect(self.on_convention_changed)

        self.wrap_check.toggled.connect(self.on_wrap_toggled)
        self.wrap_check.toggled.connect(self.update_preview)
        self.wrap_spin.valueChanged.connect(self.update_preview)
        self.character_wrap_check.toggled.connect(self.update_preview)

        self.timestamp_check.toggled.connect(self.on_timestamp_changed)

        self.ts_curly_radio.toggled.connect(self.on_timestamp_format_changed)
        self.ts_hash_radio.toggled.connect(self.on_timestamp_format_changed)
        self.ts_bracket_radio.toggled.connect(self.on_timestamp_format_changed)
        self.ts_custom_radio.toggled.connect(self.on_timestamp_format_changed)
        self.ts_custom_edit.textChanged.connect(self.update_preview)

        self.delimiter_custom.toggled.connect(self.on_custom_delimiter_toggled)
        self.concat_check.toggled.connect(self.update_preview)
        self.delimiter_default.toggled.connect(self.update_preview)
        self.delimiter_custom.toggled.connect(self.update_preview)
        self.custom_delimiter_edit.textChanged.connect(self.update_preview)

        self.diarization_check.toggled.connect(self.update_preview)
        self.blank_line_check.toggled.connect(self.update_preview)
        self.title_check.toggled.connect(self.update_preview)
        self.memo_check.toggled.connect(self.update_preview)
        self.audio_check.toggled.connect(self.update_preview)
        self.concat_check.toggled.connect(self.update_export_options_state)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # ----- Set initial states -----
        if self.timestamp_style == "curly":
            self.ts_curly_radio.setChecked(True)
        elif self.timestamp_style == "hash":
            self.ts_hash_radio.setChecked(True)
        elif self.timestamp_style == "bracket":
            self.ts_bracket_radio.setChecked(True)
        else:  # custom
            self.ts_custom_radio.setChecked(True)
            self.ts_custom_edit.setText(self.custom_timestamp_pattern)

        # Initial format update
        self.on_format_changed()
        
        
    def update_export_options_state(self):
        """Enable/disable options based on format, convention, and concatenation state."""
        is_srt = (self.export_format == "srt")
        is_gat2 = ("GAT2" in self.convention_combo.currentText())
        concat_enabled = self.concat_check.isChecked()

        # ----- SRT disables most options -----
        if is_srt:
            # Transcript Setup
            self.timestamp_check.setEnabled(False)
            self.ts_format_widget.setEnabled(False)
            self.diarization_check.setEnabled(True)   # SRT always has diarization
            self.diarization_check.setChecked(True)
            self.concat_check.setEnabled(False)
            self.delimiter_default.setEnabled(False)
            self.delimiter_custom.setEnabled(False)
            self.custom_delimiter_edit.setEnabled(False)
            self.blank_line_check.setEnabled(False)
            # Wrap controls
            self.wrap_check.setEnabled(False)
            self.wrap_spin.setEnabled(False)
            self.character_wrap_check.setEnabled(False)

            # Header Options
            self.title_check.setEnabled(False)
            self.memo_check.setEnabled(False)
            self.audio_check.setEnabled(False)
        else:
            # ----- Non‑SRT: enable appropriately -----

            # Timestamp controls
            self.timestamp_check.setEnabled(self.include_timestamps)
            self.ts_format_widget.setEnabled(self.timestamp_check.isChecked())
            self.ts_custom_edit.setEnabled(self.ts_custom_radio.isChecked() and self.timestamp_check.isChecked())

            # Diarization – always enabled but not user‑changeable (forced on)
            self.diarization_check.setEnabled(False)
            self.diarization_check.setChecked(True)

            # Concatenation checkbox – enabled only for GAT2
            self.concat_check.setEnabled(is_gat2)

            # Delimiter options – enabled only if concatenation is checked
            self.delimiter_default.setEnabled(concat_enabled)
            self.delimiter_custom.setEnabled(concat_enabled)
            self.custom_delimiter_edit.setEnabled(concat_enabled and self.delimiter_custom.isChecked())

            # Blank line after turn – always enabled (but may be forced on by convention)
            self.blank_line_check.setEnabled(True)

            # Wrap controls: spin and character wrap are enabled if wrap_check is checked,
            # regardless of whether the checkbox itself is enabled (e.g., TiQ where it's disabled but checked).
            # The checkbox's own enabled state is set by convention (on_convention_changed) and format.
            self.wrap_spin.setEnabled(self.wrap_check.isChecked())
            self.character_wrap_check.setEnabled(self.wrap_check.isChecked())       

    def on_custom_delimiter_toggled(self, checked):
        self.custom_delimiter_edit.setEnabled(checked)
        
    def on_wrap_toggled(self, checked):
        self.wrap_spin.setEnabled(checked)
        self.character_wrap_check.setEnabled(checked)

    def on_format_changed(self):
        if self.html_radio.isChecked():
            self.export_format = "html"
        elif self.docx_radio.isChecked():
            self.export_format = "docx"
        elif self.txt_radio.isChecked():
            self.export_format = "txt"
        else:
            self.export_format = "srt"

        # Determine if we are in SRT mode
        is_srt = (self.export_format == "srt")

        # Explicitly set header options enabled state
        self.title_check.setEnabled(not is_srt)
        self.memo_check.setEnabled(not is_srt)
        self.audio_check.setEnabled(not is_srt)

        # Update all other controls via the state method
        self.update_export_options_state()

        # Force a repaint of the header widgets (ensures they visually update)
        self.title_check.update()
        self.memo_check.update()
        self.audio_check.update()

        # Refresh the preview
        self.update_preview()

    def on_convention_changed(self, convention_text):
        if "Dresing" in convention_text:
            self.transcript_convention = "dresing_pehl"
            self.wrap_check.setChecked(False)
            self.wrap_check.setEnabled(False)
            self.wrap_spin.setEnabled(False)
            self.set_timestamp_style("hash")
            self.blank_line_check.setChecked(True)
            self.concat_check.setChecked(True)
            self.concat_check.setEnabled(False)   # forced on, disabled
        elif "TiQ" in convention_text:
            self.transcript_convention = "tiq"
            self.wrap_check.setChecked(True)      # TiQ uses wrapping by default
            self.wrap_check.setEnabled(False)
            self.wrap_spin.setEnabled(True)
            self.set_timestamp_style("hash")
            self.blank_line_check.setChecked(False)
            self.concat_check.setChecked(True)
            self.concat_check.setEnabled(False)   # forced on, disabled
        else:  # GAT2
            self.transcript_convention = "gat2"
            self.wrap_check.setChecked(False)     # default off
            self.wrap_check.setEnabled(True)
            self.wrap_spin.setEnabled(self.wrap_check.isChecked())
            self.set_timestamp_style("curly")
            self.blank_line_check.setChecked(False)
            self.concat_check.setChecked(False)   # default off
            self.concat_check.setEnabled(True)    # user can toggle

        self.on_wrap_toggled(self.wrap_check.isChecked())
        # Update delimiter widget enabled state (but not its checked state)
        self.update_export_options_state()
        self.update_preview()

    def set_timestamp_style(self, style):
        """Helper to set the radio buttons based on style name."""
        if style == "curly":
            self.ts_curly_radio.setChecked(True)
        elif style == "hash":
            self.ts_hash_radio.setChecked(True)
        elif style == "bracket":
            self.ts_bracket_radio.setChecked(True)
        else:
            self.ts_custom_radio.setChecked(True)
            # keep existing custom text

    def on_timestamp_format_changed(self):
        self.ts_custom_edit.setEnabled(self.ts_custom_radio.isChecked())
        self.update_preview()

    def on_timestamp_changed(self, checked):
        self.current_include_timestamps = checked
        if self.export_format != "srt":
            self.ts_format_widget.setEnabled(checked)
        self.ts_custom_edit.setEnabled(checked and self.ts_custom_radio.isChecked() and self.export_format != "srt")
        self.update_export_options_state()
        QTimer.singleShot(100, self.update_preview)

    def update_preview(self):
        main = self.main_window
        if not main:
            return

        # Determine current timestamp style and pattern
        if self.ts_curly_radio.isChecked():
            ts_style = "curly"
            custom = None
        elif self.ts_hash_radio.isChecked():
            ts_style = "hash"
            custom = None
        elif self.ts_bracket_radio.isChecked():
            ts_style = "bracket"
            custom = None
        else:
            ts_style = "custom"
            custom = self.ts_custom_edit.text()

        if self.export_format == "srt":
            srt_text = generate_srt_text(main.transcript,
                include_diarization=self.diarization_check.isChecked(),
                unassigned_handling="skip"
            )
            # generate_srt_text now strips markers internally
            self.preview_text.setPlainText(srt_text)
            return

        if self.export_format == "docx":
            self.preview_text.setPlainText("Preview not available for this format. The exported file will contain the full transcript with selected options.")
            return

        # Generate transcript text (includes markers)
        transcript_text = generate_transcript_text(main.transcript, 
            include_timestamps=self.current_include_timestamps,
            timestamp_style=ts_style,
            custom_pattern=custom,
            convention=self.transcript_convention,
            include_diarization=self.diarization_check.isChecked(),
            wrap_enabled=self.wrap_check.isChecked(),
            wrap_length=self.wrap_spin.value(),
            character_wrap=self.character_wrap_check.isChecked(),
            add_blank_line=self.blank_line_check.isChecked(),
            concatenate_turns=self.concat_check.isChecked(),
            delimiter_choice=self.get_delimiter_choice(),
            custom_delimiter=self.custom_delimiter_edit.text()
        )

        # Build header (plain text, used only for TXT preview; HTML header is built by build_html_content)
        header_lines = []
        if self.title_check.isChecked() and main.project_name:
            header_lines.append(main.project_name)
            header_lines.append("=" * len(main.project_name))
            header_lines.append("")
        if self.memo_check.isChecked() and main.project_memo:
            header_lines.append(f"Project Memo: {main.project_memo}")
            header_lines.append("")
        if self.audio_check.isChecked() and main.audio_file_path:
            audio_name = Path(main.audio_file_path).name
            header_lines.append(f"Audio File: {audio_name}")
            header_lines.append("")

        header = "\n".join(header_lines) + "\n" if header_lines else ""

        if self.export_format == "html":
            # Build HTML content using the shared builder
            html_content = build_html_content(
                transcript_text,
                {
                    'convention': self.transcript_convention,
                    'include_title': self.title_check.isChecked(),
                    'include_memo': self.memo_check.isChecked(),
                    'include_audio': self.audio_check.isChecked(),
                },
                {'name': main.project_name, 'memo': main.project_memo},
                main.audio_file_path
            )
            self.preview_text.setHtml(html_content)
        else:  # TXT
            # For plain text, strip markers
            stripped_text = strip_markup(transcript_text)
            self.preview_text.setPlainText(header + stripped_text)

    def get_export_settings(self):
        if self.ts_curly_radio.isChecked():
            ts_style = "curly"
        elif self.ts_hash_radio.isChecked():
            ts_style = "hash"
        elif self.ts_bracket_radio.isChecked():
            ts_style = "bracket"
        else:
            ts_style = "custom"

        custom_pattern = self.ts_custom_edit.text() if ts_style == "custom" else ""
        
        delim_choice = self.get_delimiter_choice()
        custom = self.custom_delimiter_edit.text() if delim_choice == "custom" else ""

        return {
            'format': self.export_format,
            'convention': self.transcript_convention,
            'include_timestamps': self.current_include_timestamps,
            'include_diarization': self.diarization_check.isChecked(),
            'include_title': self.title_check.isChecked(),
            'include_memo': self.memo_check.isChecked(),
            'include_audio': self.audio_check.isChecked(),
            'wrap_enabled': self.wrap_check.isChecked(),
            'wrap_length': self.wrap_spin.value(),
            'character_wrap': self.character_wrap_check.isChecked(),
            'timestamp_style': ts_style,
            'custom_timestamp_pattern': custom_pattern,
            'add_blank_line': self.blank_line_check.isChecked(),
            'delimiter_choice': delim_choice,
            'custom_delimiter': custom
        }
    
    def get_delimiter_choice(self):
        if self.delimiter_default.isChecked():
            return "default"
        else:
            return "custom"
        
class SearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.current_match = 0
        self.total_matches = 0
        self.match_positions = []  # List of (block_index, start_pos, end_pos)
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Search")
        self.setGeometry(300, 200, 500, 150)
        
        layout = QVBoxLayout(self)
        
        # Search input
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term")
        self.search_input.textChanged.connect(self.perform_search)
        search_layout.addWidget(self.search_input)
        
        self.case_sensitive_check = QCheckBox("Case sensitive")
        self.case_sensitive_check.toggled.connect(self.perform_search)
        search_layout.addWidget(self.case_sensitive_check)
        
        layout.addLayout(search_layout)
        
        # Match information and navigation
        nav_layout = QHBoxLayout()
        
        self.match_label = QLabel("0 matches")
        nav_layout.addWidget(self.match_label)
        
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.clicked.connect(self.previous_match)
        self.prev_button.setEnabled(False)
        nav_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(self.next_match)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button)
        
        layout.addLayout(nav_layout)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setFocus()
        self.search_input.setFocus()
        
    def perform_search(self):
        search_term = self.search_input.text()
        case_sensitive = self.case_sensitive_check.isChecked()
        
        if not search_term:
            self.match_label.setText("0 matches")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.match_positions = []
            self.total_matches = 0
            if self.parent:
                self.parent.clear_search_highlights()
            return
            
        self.match_positions = []
        
        # Search through all blocks
        for block_idx, block in enumerate(self.parent.srt_blocks):
            text = block['text']
            if not text:
                continue
                
            if case_sensitive:
                search_in = text
            else:
                search_in = text.lower()
                search_term_lower = search_term.lower()
            
            start_pos = 0
            while True:
                if case_sensitive:
                    pos = search_in.find(search_term, start_pos)
                else:
                    pos = search_in.find(search_term_lower, start_pos)
                    
                if pos == -1:
                    break
                    
                self.match_positions.append((block_idx, pos, pos + len(search_term)))
                start_pos = pos + 1
        
        self.total_matches = len(self.match_positions)
        self.current_match = 0
        
        if self.total_matches > 0:
            self.match_label.setText(f"{self.current_match + 1}/{self.total_matches} matches")
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
            self.highlight_current_match()
        else:
            self.match_label.setText("0 matches")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            
    def highlight_current_match(self):
        if not self.match_positions or self.current_match >= len(self.match_positions):
            return
            
        block_idx, start_pos, end_pos = self.match_positions[self.current_match]
        
        if self.parent:
            self.parent.highlight_search_match(block_idx, start_pos, end_pos)
            
    def next_match(self):
        if self.total_matches == 0:
            return
            
        self.current_match = (self.current_match + 1) % self.total_matches
        self.match_label.setText(f"{self.current_match + 1}/{self.total_matches} matches")
        self.highlight_current_match()
        
    def previous_match(self):
        if self.total_matches == 0:
            return
            
        self.current_match = (self.current_match - 1) % self.total_matches
        self.match_label.setText(f"{self.current_match + 1}/{self.total_matches} matches")
        self.highlight_current_match()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
        elif event.key() == Qt.Key_F3 and event.modifiers() & Qt.ShiftModifier:
            self.previous_match()
            event.accept()
        elif event.key() == Qt.Key_F3:
            self.next_match()
            event.accept()
        elif event.key() == Qt.Key_G and event.modifiers() == Qt.ControlModifier:
            self.next_match()
            event.accept()
        else:
            super().keyPressEvent(event)

class JumpToTimeDialog(QDialog):
    def __init__(self, max_duration_ms, parent=None):
        super().__init__(parent)
        self.max_duration_ms = max_duration_ms
        self.target_time_ms = 0
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Jump to Time")
        self.setGeometry(300, 300, 400, 200)
        
        layout = QVBoxLayout(self)
        
        instructions = QLabel("Enter time to jump to (format: MM:SS or HH:MM:SS):")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        self.time_edit = QLineEdit()
        self.time_edit.setPlaceholderText("e.g., 1:30 or 0:01:30")
        layout.addWidget(self.time_edit)
        
        # Current max time display
        max_minutes = self.max_duration_ms // 60000
        max_seconds = (self.max_duration_ms % 60000) // 1000
        max_hours = max_minutes // 60
        max_minutes = max_minutes % 60
        
        max_time_label = QLabel(f"Maximum time: {max_hours:02d}:{max_minutes:02d}:{max_seconds:02d}")
        layout.addWidget(max_time_label)
        
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.time_edit.setFocus()
        
    def validate_and_accept(self):
        time_str = self.time_edit.text().strip()
        if not time_str:
            self.error_label.setText("Please enter a time")
            return
            
        # Parse time format (MM:SS or HH:MM:SS)
        parts = time_str.split(':')
        if len(parts) == 2:
            # MM:SS format
            try:
                minutes = int(parts[0])
                seconds = int(parts[1])
                hours = 0
            except ValueError:
                self.error_label.setText("Invalid time format")
                return
        elif len(parts) == 3:
            # HH:MM:SS format
            try:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
            except ValueError:
                self.error_label.setText("Invalid time format")
                return
        else:
            self.error_label.setText("Use MM:SS or HH:MM:SS format")
            return
            
        # Validate time values
        if minutes >= 60 or seconds >= 60:
            self.error_label.setText("Minutes and seconds must be less than 60")
            return
            
        self.target_time_ms = (hours * 3600 + minutes * 60 + seconds) * 1000
        
        if self.target_time_ms > self.max_duration_ms:
            self.error_label.setText("Time exceeds audio duration")
            return
            
        self.accept()
        
    def get_target_time(self):
        return self.target_time_ms
    
class EnhancedPlacementDialog(QDialog):
    """Enhanced placement dialog that handles different symbol types"""
    
    def __init__(self, current_text, symbol_info, parent=None):
        super().__init__(parent)
        self.current_text = current_text
        self.symbol_info = symbol_info
        self.placement_position = 0
        self.create_new_line = False
        self.selected_text_start = 0
        self.selected_text_end = 0
        self.has_selection = False
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle(f"Insert {self.symbol_info.get('category', 'Symbol').title()}")
        self.setGeometry(300, 300, 700, 400)

        layout = QVBoxLayout(self)
        
        # Instructions based on symbol type
        instructions = self.get_instructions()
        instructions_label = QLabel(instructions)
        instructions_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions_label)
        
        # Text display with selection capability
        self.text_display = QTextEdit()
        self.text_display.setPlainText(self.current_text)
        self.text_display.setMaximumHeight(150)
        self.text_display.setStyleSheet("""
            font-family: monospace;
            font-size: 14px;
            background-color: palette(base);
            color: palette(text);
            border: 2px solid palette(mid);
            selection-background-color: palette(highlight);
            selection-color: palette(highlighted-text);
        """)
        layout.addWidget(self.text_display)
        
        # Selection info
        self.selection_label = QLabel("No text selected")
        layout.addWidget(self.selection_label)
        
        # Options
        self.option_label = QLabel("")
        self.update_option_label()
        layout.addWidget(self.option_label)
        
        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        for button in button_box.buttons():
            button.setFocusPolicy(Qt.NoFocus)
            
        layout.addWidget(button_box)
        
        # Connect signals
        self.text_display.selectionChanged.connect(self.on_selection_changed)
        
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        self.text_display.setFocus()
        
    def get_instructions(self):
        """Get instructions based on symbol type"""
        category = self.symbol_info.get('category', '').lower()
        
        if 'dresing' in category:
            return "Dresing & Pehl: Use ← → to position, select text with mouse, Enter to confirm, N for new line"
        elif 'tiq' in category:
            return "TiQ: Use ← → to position, select text with mouse, Enter to confirm, N for new line"
        elif 'custom' in category:
            symbol_type = self.symbol_info.get('type', 'simple')
            if symbol_type in ['wrapper', 'comment', 'comment_reach']:
                return f"Select the text to wrap with {self.symbol_info.get('display', 'symbol')}"
            else:
                return "Use ← → to position, Enter to confirm, N for new line"
        else:  # GAT2
            return "Use ← → to position, select text with mouse, Enter to confirm, N for new line"
    
    def on_selection_changed(self):
        """Handle text selection changes"""
        cursor = self.text_display.textCursor()
        if cursor.hasSelection():
            self.has_selection = True
            self.selected_text_start = cursor.selectionStart()
            self.selected_text_end = cursor.selectionEnd()
            selected_text = cursor.selectedText()
            self.selection_label.setText(f"Selected: '{html.escape(selected_text)}'")
        else:
            self.has_selection = False
            self.selection_label.setText("No text selected")
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left and not event.modifiers():
            # Move cursor left
            cursor = self.text_display.textCursor()
            cursor.movePosition(cursor.Left)
            self.text_display.setTextCursor(cursor)
            event.accept()
        elif event.key() == Qt.Key_Right and not event.modifiers():
            # Move cursor right
            cursor = self.text_display.textCursor()
            cursor.movePosition(cursor.Right)
            self.text_display.setTextCursor(cursor)
            event.accept()
        elif event.key() == Qt.Key_N:
            self.create_new_line = not self.create_new_line
            self.update_option_label()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ControlModifier:
                # Ctrl+Enter to accept
                self.accept()
                event.accept()
            else:
                # Regular Enter passes to text edit for new line
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
    
    def update_option_label(self):
        if self.create_new_line:
            self.option_label.setText("Option: Create new line (Press N for inline)")
        else:
            self.option_label.setText("Option: Insert in current line (Press N for new line)")
    
    def get_placement_result(self):
        """Get the result of placement based on symbol type"""
        symbol_type = self.symbol_info.get('type', 'builtin')
        display = self.symbol_info.get('display', '')
        
        # New line option (only allowed for simple symbols)
        if self.create_new_line:
            return {
                'action': 'new_line',
                'text': display
            }
        
        current_text = self.text_display.toPlainText()
        
        if self.has_selection:
            selected_text = current_text[self.selected_text_start:self.selected_text_end]
            
            # Handle wrapper symbols (custom or built-in wrappers)
            if symbol_type in ['wrapper', 'comment', 'comment_reach']:
                left = self.symbol_info.get('left', '')
                right = self.symbol_info.get('right', '')
                # For built-in wrappers without explicit left/right, derive from display
                if not left and display == '@(   )@':
                    left = '@('
                    right = ')@'
                elif not left and display == '°   °':
                    left = '°'
                    right = '°'
                elif not left and display == '//   //':
                    left = '//'
                    right = '//'
                new_text = (current_text[:self.selected_text_start] + left + selected_text + right +
                           current_text[self.selected_text_end:])
                return {'action': 'replace', 'text': new_text}
            else:
                # For simple symbols, ignore selection and insert at cursor position
                cursor = self.text_display.textCursor()
                pos = cursor.position()
                new_text = current_text[:pos] + " " + display + " " + current_text[pos:]
                return {'action': 'replace', 'text': new_text}
        else:
            # No selection: insert at cursor
            cursor = self.text_display.textCursor()
            pos = cursor.position()
            new_text = current_text[:pos] + " " + display + " " + current_text[pos:]
            return {'action': 'replace', 'text': new_text}
        
class PlacementDialog(QDialog):
    def __init__(self, current_text, symbol, parent=None, cjk_mode=False):
        super().__init__(parent)
        self.current_text = current_text
        self.symbol = symbol
        self.placement_position = 0
        self.create_new_line = False
        self.cjk_mode = cjk_mode
        self.dark = _is_dark_theme(self)
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Place Symbol")
        self.setGeometry(300, 300, 600, 300)

        layout = QVBoxLayout(self)

        instructions = QLabel("Use ← → arrows to position, Enter to confirm, N for new line:")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)

        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setMaximumHeight(100)
        self.text_display.setStyleSheet("""
            font-family: monospace;
            font-size: 14px;
            background-color: palette(base);
            color: palette(text);
            border: 2px solid palette(mid);
            selection-background-color: palette(highlight);
            selection-color: palette(highlighted-text);
        """)
        layout.addWidget(self.text_display)

        self.option_label = QLabel("Placement: Insert in current line (Press N to create new line)")
        layout.addWidget(self.option_label)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        for button in button_box.buttons():
            button.setFocusPolicy(Qt.NoFocus)

        layout.addWidget(button_box)

        self.update_display()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.placement_position = max(0, self.placement_position - 1)
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Right:
            self.placement_position = min(len(self.current_text), self.placement_position + 1)
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_N:
            self.create_new_line = not self.create_new_line
            self.update_display()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def get_inserted_text(self, pos):
        """Return new text after inserting symbol at pos with proper spacing."""
        left = self.current_text[:pos]
        right = self.current_text[pos:]
        
        if self.cjk_mode:
            # No spaces around symbol
            return left + self.symbol + right
        else:
            # Latin: add spaces but avoid double spaces
            # Check if left ends with space
            if left and not left[-1].isspace():
                left += ' '
            # Check if right starts with space
            if right and not right[0].isspace():
                symbol = self.symbol + ' '
            else:
                symbol = self.symbol
            return left + symbol + right
    
    def update_display(self):
        if self.dark:
            text_bg = "#3a3a3a"
            symbol_bg = "#3a5a3a"
        else:
            text_bg = "#e0e0e0"
            symbol_bg = "#c8f7c8"

        if self.create_new_line:
            html_content = f"""
            <div style="font-family: monospace; font-size: 14px; padding: 10px;">
                <span style="background-color: {text_bg}; padding: 5px; border-radius: 3px;">{html.escape(self.current_text)}</span><br>
                <span style="background-color: {symbol_bg}; padding: 5px; border-radius: 3px;">{html.escape(self.symbol)}</span>
            </div>
            """
            self.option_label.setText("Placement: Create new line with symbol (Press N for inline)")
        else:
            before_text = self.current_text[:self.placement_position]
            after_text = self.current_text[self.placement_position:]
            html_content = f"""
            <div style="font-family: monospace; font-size: 14px; padding: 10px;">
                <span style="background-color: {text_bg}; padding: 5px; border-radius: 3px;">{html.escape(before_text)}</span>
                <span style="background-color: {symbol_bg}; padding: 5px; border-radius: 3px;">{html.escape(self.symbol)}</span>
                <span style="background-color: {text_bg}; padding: 5px; border-radius: 3px;">{html.escape(after_text)}</span>
            </div>
            """
            self.option_label.setText("Placement: Insert in current line (Press N to create new line)")
        
        self.text_display.setHtml(html_content)

    def get_result(self):
        """Return (create_new_line, new_text_for_inline) if not new line, else (True, symbol)"""
        if self.create_new_line:
            return True, self.symbol
        else:
            return False, self.get_inserted_text(self.placement_position)
