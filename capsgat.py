import sys
import re
import json
import os
import math
import tempfile
import webbrowser
import logging
import vlc
from pathlib import Path
from datetime import datetime
from collections import deque
import queue
import threading
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QListWidget, QPushButton, QWidget, QLabel, 
                             QFileDialog, QMessageBox, QSpinBox, QShortcut, QFrame,
                             QInputDialog, QLineEdit, QDialog, QDialogButtonBox, 
                             QGridLayout, QPlainTextEdit, QCheckBox, QTabWidget, QRadioButton,
                             QSlider, QProgressBar, QMenuBar, QMenu, QAction, QFontDialog,
                             QGroupBox, QScrollArea, QSizePolicy, QComboBox)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QPoint, QRect, QElapsedTimer, QThread
from PyQt5.QtGui import QFont, QKeySequence, QColor, QTextCharFormat, QSyntaxHighlighter, QIcon, QPainter, QPen, QBrush, QPainterPath

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import pyaudio
    import soundfile as sf
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    logger.warning("PyAudio not installed. Fallback audio will not work.")
    
try:
    import vlc
    VLC_AVAILABLE = True
    logger.info("VLC library is available")
except Exception as e:
    VLC_AVAILABLE = False
    logger.warning(f"VLC library not available: {e}")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class SimpleAudioPlayer(QThread):
    """Simple fallback audio player using PyAudio (no speed control)"""
    playback_started = pyqtSignal()
    playback_stopped = pyqtSignal()
    position_changed = pyqtSignal(float)  # Position in seconds
    
    def __init__(self):
        super().__init__()
        self.audio_path = None
        self.is_playing = False
        self.is_paused = False
        self.stop_flag = False
        self.current_position = 0.0
        self.duration = 0.0
        self.sample_rate = 44100
        self.channels = 1
        self.pyaudio = None
        self.stream = None
        self.audio_data = None
        
    def load_file(self, audio_path):
        """Load audio file"""
        try:
            self.audio_path = audio_path
            
            # Load audio data
            audio_data, self.sample_rate = sf.read(audio_path)
            
            # Convert to mono if needed
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)
            
            # Convert to int16
            if audio_data.dtype != np.int16:
                audio_data = (audio_data * 32767).astype(np.int16)
            
            self.audio_data = audio_data.tobytes()
            self.duration = len(audio_data) / self.sample_rate
            self.channels = 1
            
            logger.info(f"Simple audio loaded: {self.duration:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load audio for fallback: {e}")
            return False
    
    def play(self):
        """Start playback"""
        if not HAS_PYAUDIO:
            logger.error("PyAudio not available for fallback")
            return
        
        self.is_playing = True
        self.is_paused = False
        self.stop_flag = False
        
        if not self.isRunning():
            self.start()
        
        self.playback_started.emit()
    
    def pause(self):
        """Pause playback"""
        self.is_playing = False
        self.is_paused = True
        
        if self.stream and self.stream.is_active():
            self.stream.stop_stream()
    
    def stop(self):
        """Stop playback"""
        self.stop_flag = True
        self.is_playing = False
        self.is_paused = False
        self.current_position = 0.0
        
        if self.stream and self.stream.is_active():
            self.stream.stop_stream()
        
        self.playback_stopped.emit()
    
    def seek(self, position_seconds):
        """Seek to position"""
        self.current_position = max(0, min(self.duration, position_seconds))
        
        # Stop and restart if playing
        if self.is_playing and not self.is_paused:
            self.stop()
            self.play()
    
    def get_position(self):
        """Get current position"""
        return self.current_position
    
    def run(self):
        """Main playback thread"""
        if not HAS_PYAUDIO or not self.audio_data:
            logger.error("Fallback player: No PyAudio or audio data")
            return
        
        try:
            import numpy as np
            import pyaudio
            
            self.pyaudio = pyaudio.PyAudio()
            
            # Calculate start position in bytes
            start_byte = int(self.current_position * self.sample_rate * 2)  # 2 bytes per sample for int16
            
            # Open stream
            self.stream = self.pyaudio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                output=True
            )
            
            # Play from current position
            chunk_size = 1024
            data_bytes = len(self.audio_data)
            
            for i in range(start_byte, data_bytes, chunk_size):
                if self.stop_flag:
                    break
                
                if not self.is_playing or self.is_paused:
                    time.sleep(0.01)
                    continue
                
                chunk = self.audio_data[i:i+chunk_size]
                if chunk:
                    self.stream.write(chunk)
                    
                    # Update position
                    self.current_position = i / (self.sample_rate * 2)
                    self.position_changed.emit(self.current_position)
                    
                    # Check if at end
                    if i + chunk_size >= data_bytes:
                        self.stop()
                        break
                
                time.sleep(chunk_size / (self.sample_rate * 2))  # Approximate timing
            
        except Exception as e:
            logger.error(f"Error in fallback player: {e}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.pyaudio:
                self.pyaudio.terminate()
    
    def cleanup(self):
        """Clean up resources"""
        self.stop()
        if self.isRunning():
            self.quit()
            self.wait()

class VlcAudioPlayer(QThread):
    """Audio player using VLC media player"""
    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    playback_stopped = pyqtSignal()
    position_changed = pyqtSignal(float)  # Position in seconds
    end_reached = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.media = None
        self.is_playing = False
        self.duration = 0.0
        self.current_position = 0.0
        self.playback_speed = 1.0
        self.audio_file_path = None
        
        # Timer for position updates
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.update_position)
        self.position_timer.start(100)  # Update every 100ms
        
        # Event manager for VLC events
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)
        
    def load_file(self, audio_path):
        """Load audio file"""
        try:
            self.audio_file_path = audio_path
            self.media = self.instance.media_new(audio_path)
            self.player.set_media(self.media)
            
            # Get duration
            self.media.parse()
            time.sleep(0.1)  # Give VLC time to parse
            self.duration = self.media.get_duration() / 1000.0  # Convert ms to seconds
            
            # Set initial speed
            self.player.set_rate(1.0)
            self.playback_speed = 1.0
            
            logger.info(f"Audio loaded: {audio_path}, duration: {self.duration:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load audio with VLC: {e}")
            return False
    
    def play(self):
        """Start playback"""
        if self.player.play() == 0:
            self.is_playing = True
            self.playback_started.emit()
            logger.info("Playback started")
        else:
            logger.error("Failed to start playback")
    
    def pause(self):
        """Pause playback"""
        self.player.pause()
        self.is_playing = False
        self.playback_paused.emit()
        logger.info("Playback paused")
    
    def stop(self):
        """Stop playback"""
        self.player.stop()
        self.is_playing = False
        self.current_position = 0.0
        self.playback_stopped.emit()
        logger.info("Playback stopped")
    
    def seek(self, position_seconds):
        """Seek to position in seconds"""
        try:
            # Convert seconds to milliseconds for VLC
            position_ms = int(position_seconds * 1000)
            self.player.set_time(position_ms)
            self.current_position = position_seconds
            self.position_changed.emit(position_seconds)
            logger.debug(f"Seeked to {position_seconds:.2f}s")
        except Exception as e:
            logger.error(f"Error seeking: {e}")
    
    def set_speed(self, speed):
        """Set playback speed (0.5 to 2.0)"""
        try:
            # VLC supports rate from 0.25 to 4.0
            speed = max(0.25, min(4.0, speed))
            self.player.set_rate(speed)
            self.playback_speed = speed
            logger.info(f"Playback speed set to {speed:.1f}x")
            return True
        except Exception as e:
            logger.error(f"Error setting playback speed: {e}")
            return False
    
    def get_position(self):
        """Get current position in seconds"""
        try:
            # VLC returns time in milliseconds
            time_ms = self.player.get_time()
            if time_ms >= 0:
                self.current_position = time_ms / 1000.0
            return self.current_position
        except:
            return self.current_position
    
    def get_state(self):
        """Get current player state"""
        return self.player.get_state()
    
    def update_position(self):
        """Update and emit current position"""
        if self.is_playing:
            pos = self.get_position()
            if pos >= 0:
                self.position_changed.emit(pos)
                
                # Check if we've reached the end
                if self.duration > 0 and pos >= self.duration - 0.1:
                    self.stop()
    
    def _on_end_reached(self, event):
        """Handle end of media"""
        self.is_playing = False
        self.end_reached.emit()
        logger.info("End of media reached")
    
    def cleanup(self):
        """Clean up resources"""
        self.position_timer.stop()
        self.stop()
        if self.player:
            self.player.release()
        if self.instance:
            self.instance.release()

class TextSelectionDialog(QDialog):
    def __init__(self, block_text, parent=None):
        super().__init__(parent)
        self.block_text = block_text
        self.start_pos = 0
        self.end_pos = 0
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
        
        html_content = f"""
        <div style="font-family: monospace; font-size: 14px; padding: 10px;">
            <span style="background-color: #e0e0e0; padding: 5px; border-radius: 3px;">{before_text}</span>
            <span style="background-color: #ffcc00; padding: 5px; border-radius: 3px;">{selected_text}</span>
            <span style="background-color: #e0e0e0; padding: 5px; border-radius: 3px;">{after_text}</span>
        </div>
        """
        
        self.text_display.setHtml(html_content)
        
        if self.start_pos == self.end_pos:
            self.selection_label.setText(f"Selection: (none) - Position: {self.start_pos}")
        else:
            self.selection_label.setText(f"Selection: '{selected_text}' (positions {self.start_pos}-{self.end_pos})")
    
    def get_selection(self):
        return self.start_pos, self.end_pos, self.block_text[self.start_pos:self.end_pos]

class BlockSplitDialog(QDialog):
    def __init__(self, block_text, parent=None):
        super().__init__(parent)
        self.block_text = block_text
        self.split_position = 0
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
        
        html_content = f"""
        <div style="font-family: monospace; font-size: 14px; padding: 10px;">
            <span style="background-color: #c8f7c8; padding: 5px; border-radius: 3px;">{before_text}</span>
            <span style="background-color: #f7c8c8; padding: 5px; border-radius: 3px;">{after_text}</span>
        </div>
        """
        
        self.text_display.setHtml(html_content)
        self.cursor_label.setText(f"Split position: {self.split_position} (text will be split after character {self.split_position})")

class EnhancedPauseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_option = 0
        self.pause_options = [
            "(.)", "(-)", "(--)", "(---)", "(_._)", "(())", "<<>>", "[ ]",
            "°h", "°hh", "°hhh", "h°", "hh°", "hhh°"
        ]
        self.pause_descriptions = [
            "micropause", "short pause", "medium pause", "long pause", 
            "measured pause", "comment", "action", "overlap",
            "short inhale", "medium inhale", "long inhale", 
            "short exhale", "medium exhale", "long exhale"
        ]
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Insert GAT2 Symbol")
        self.setGeometry(300, 300, 650, 350)
        
        layout = QVBoxLayout(self)
        
        # Create a grid to show all options with highlighting
        self.option_widget = QWidget()
        option_layout = QGridLayout(self.option_widget)
        
        self.option_labels = []
        for i, (symbol, desc) in enumerate(zip(self.pause_options, self.pause_descriptions)):
            # Escape HTML in the symbol for display
            escaped_symbol = (symbol.replace('&', '&amp;')
                                   .replace('<', '&lt;')
                                   .replace('>', '&gt;'))
            
            label = QLabel(f"<b>{escaped_symbol}</b>")  # Use escaped symbol here
            label.setAlignment(Qt.AlignCenter)
            label.setToolTip(desc)
            label.setStyleSheet("""
                QLabel {
                    border: 2px solid #ccc;
                    border-radius: 8px;
                    padding: 15px;
                    margin: 3px;
                    background-color: #f0f0f0;
                    font-size: 14px;
                }
                QLabel:hover {
                    background-color: #e0e0e0;
                }
            """)
            label.setMinimumSize(80, 60)
            label.mousePressEvent = lambda event, idx=i: self.label_clicked(idx)
            option_layout.addWidget(label, i // 4, i % 4)
            self.option_labels.append(label)
        
        layout.addWidget(self.option_widget)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        for button in button_box.buttons():
            button.setFocusPolicy(Qt.NoFocus)
            
        layout.addWidget(button_box)
        
        self.update_display()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        
    def label_clicked(self, index):
        self.selected_option = index
        self.update_display()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.selected_option = (self.selected_option - 1) % len(self.pause_options)
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Right:
            self.selected_option = (self.selected_option + 1) % len(self.pause_options)
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Up:
            self.selected_option = (self.selected_option - 4) % len(self.pause_options)
            self.update_display()
            event.accept()
        elif event.key() == Qt.Key_Down:
            self.selected_option = (self.selected_option + 4) % len(self.pause_options)
            self.update_display()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def update_display(self):
        # Update all labels, highlighting the selected one
        for i, label in enumerate(self.option_labels):
            if i == self.selected_option:
                label.setStyleSheet("""
                    QLabel {
                        border: 3px solid #ff6600;
                        border-radius: 8px;
                        padding: 15px;
                        margin: 3px;
                        background-color: #fff0cc;
                        font-weight: bold;
                        font-size: 14px;
                    }
                """)
            else:
                label.setStyleSheet("""
                    QLabel {
                        border: 2px solid #ccc;
                        border-radius: 8px;
                        padding: 15px;
                        margin: 3px;
                        background-color: #f0f0f0;
                        font-size: 14px;
                    }
                    QLabel:hover {
                        background-color: #e0e0e0;
                    }
                """)

class PlacementDialog(QDialog):
    def __init__(self, current_text, symbol, parent=None):
        super().__init__(parent)
        self.current_text = current_text
        self.symbol = symbol
        self.placement_position = 0
        self.create_new_line = False
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
        self.text_display.setStyleSheet("font-family: monospace; font-size: 14px;")
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
    
    def update_display(self):
        if self.create_new_line:
            html_content = f"""
            <div style="font-family: monospace; font-size: 14px; padding: 10px;">
                <span style="background-color: #e0e0e0; padding: 5px; border-radius: 3px;">{self.current_text}</span><br>
                <span style="background-color: #c8f7c8; padding: 5px; border-radius: 3px;">{self.symbol}</span>
            </div>
            """
            self.option_label.setText("Placement: Create new line with symbol (Press N for inline)")
        else:
            before_text = self.current_text[:self.placement_position]
            after_text = self.current_text[self.placement_position:]
            html_content = f"""
            <div style="font-family: monospace; font-size: 14px; padding: 10px;">
                <span style="background-color: #e0e0e0; padding: 5px; border-radius: 3px;">{before_text}</span>
                <span style="background-color: #c8f7c8; padding: 5px; border-radius: 3px;">{self.symbol}</span>
                <span style="background-color: #e0e0e0; padding: 5px; border-radius: 3px;">{after_text}</span>
            </div>
            """
            self.option_label.setText("Placement: Insert in current line (Press N to create new line)")
        
        self.text_display.setHtml(html_content)

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

class EditDialog(QDialog):
    def __init__(self, current_text, parent=None):
        super().__init__(parent)
        self.edited_text = current_text
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Edit Segment Content")
        self.setGeometry(300, 300, 600, 300)
        
        layout = QVBoxLayout(self)
        
        instructions = QLabel("Edit the segment content:")
        instructions.setStyleSheet("font-weight: bold;")
        layout.addWidget(instructions)
        
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(self.edited_text)
        self.text_edit.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(self.text_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.text_edit.setFocus()
        
    def get_text(self):
        return self.text_edit.toPlainText()

class SettingsDialog(QDialog):
    def __init__(self, current_font, current_theme, parent=None):  # Add current_theme parameter
        super().__init__(parent)
        self.selected_font = current_font
        self.current_theme = current_theme  # Store it
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Settings")
        self.setGeometry(100, 100, 120, 120)
        
        layout = QVBoxLayout(self)
        
        # Font selection
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Text Display Font:"))
        
        self.font_button = QPushButton(f"{self.selected_font.family()} {self.selected_font.pointSize()}pt")
        self.font_button.clicked.connect(self.select_font)
        font_layout.addWidget(self.font_button)
        font_layout.addStretch()
        
        layout.addLayout(font_layout)
        
        theme_layout = QHBoxLayout()
        
        theme_layout.addWidget(QLabel("Viewer Theme:"))

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setCurrentText("Light")  # Default
        self.theme_combo.setCurrentText(self.current_theme.capitalize())
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()

        layout.addLayout(theme_layout)
                
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
        return self.theme_combo.currentText().lower()

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
    def __init__(self, parent=None, has_timestamps=True, project_info=None, audio_path=None):
        super().__init__(parent)
        self.include_timestamps = has_timestamps
        self.current_include_timestamps = has_timestamps
        self.export_format = "html"  # Default to HTML
        self.transcript_convention = "gat2"  # Default to GAT2
        self.project_info = project_info or {}
        self.audio_path = audio_path
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Export Preview")
        self.setGeometry(100, 100, 850, 750)  # Increased height
        
        layout = QVBoxLayout(self)
        
        # Format selection - use radio buttons
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Export Format:"))
        
        # Changed order: HTML, DOCX TXT, SRT
        self.html_radio = QRadioButton("HTML (.html)")
        self.html_radio.setChecked(True)
        self.html_radio.toggled.connect(self.on_format_changed)
        
        self.docx_radio = QRadioButton("Word Document (.docx)")
        self.docx_radio.toggled.connect(self.on_format_changed)
               
        self.txt_radio = QRadioButton("Plain Text (.txt)")
        self.txt_radio.toggled.connect(self.on_format_changed)
        
        self.srt_radio = QRadioButton("Subtitle File (.srt)")
        self.srt_radio.toggled.connect(self.on_format_changed)
        
        format_layout.addWidget(self.html_radio)
        format_layout.addWidget(self.docx_radio)
        format_layout.addWidget(self.txt_radio)
        format_layout.addWidget(self.srt_radio)
        format_layout.addStretch()
        
        # Disable SRT radio if no timestamps
        if not self.include_timestamps:
            self.srt_radio.setEnabled(False)
            self.srt_radio.setToolTip("SRT export requires timestamp information. Original file does not contain timestamps.")
        
        # Convention selection
        convention_layout = QHBoxLayout()
        convention_layout.addWidget(QLabel("Transcript Convention:"))
        
        self.convention_combo = QComboBox()
        self.convention_combo.addItems(["GAT2 (Conversation Analysis)", "Dresing & Pehl (Sociological Interviews)"])
        self.convention_combo.currentTextChanged.connect(self.on_convention_changed)
        convention_layout.addWidget(self.convention_combo)
        convention_layout.addStretch()
        
        # Options group
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout()
        
        # Timestamp option (disabled for SRT since SRT always has timestamps)
        self.timestamp_check = QCheckBox("Include timestamps")
        self.timestamp_check.setChecked(self.include_timestamps)
        self.timestamp_check.setEnabled(self.include_timestamps)
        self.timestamp_check.toggled.connect(self.on_timestamp_changed)
        
        if not self.include_timestamps:
            self.timestamp_check.setToolTip("Timestamps not available for text file imports")
        
        # Diarization option
        self.diarization_check = QCheckBox("Include diarization (speaker labels)")
        self.diarization_check.setChecked(True)
        self.diarization_check.toggled.connect(self.update_preview)
        
        # Project info options
        self.title_check = QCheckBox("Include project title")
        self.title_check.setChecked(True)
        self.title_check.toggled.connect(self.update_preview)
        
        self.memo_check = QCheckBox("Include project memo") 
        self.memo_check.setChecked(True)
        self.memo_check.toggled.connect(self.update_preview)
        
        self.audio_check = QCheckBox("Include audio file path")
        self.audio_check.setChecked(True)
        self.audio_check.toggled.connect(self.update_preview)
        
        options_layout.addWidget(self.timestamp_check)
        options_layout.addWidget(self.diarization_check)
        options_layout.addWidget(self.title_check)
        options_layout.addWidget(self.memo_check)
        options_layout.addWidget(self.audio_check)
        options_group.setLayout(options_layout)
        
        # Preview area
        preview_label = QLabel("Preview:")
        preview_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        
        # Initial setup for format and convention
        self.on_format_changed()
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addLayout(format_layout)
        layout.addLayout(convention_layout)
        layout.addWidget(options_group)
        layout.addWidget(preview_label)
        layout.addWidget(self.preview_text)
        layout.addWidget(button_box)
        
    def on_format_changed(self):
        if self.html_radio.isChecked():
            self.export_format = "html"
        elif self.docx_radio.isChecked():
            self.export_format = "docx"
        elif self.txt_radio.isChecked():
            self.export_format = "txt"
        else:  # SRT format
            self.export_format = "srt"
        
        # Enable/disable options based on format
        is_srt = (self.export_format == "srt")
        
        # For SRT: disable project info options, enable diarization
        self.title_check.setEnabled(not is_srt)
        self.memo_check.setEnabled(not is_srt)
        self.audio_check.setEnabled(not is_srt)
        self.timestamp_check.setEnabled(not is_srt and self.include_timestamps)
        
        # Diarization logic: For SRT, enable it. For non-SRT and GAT2, disable and check. For non-SRT and Dresing & Pehl, disable and check.
        if is_srt:
            self.diarization_check.setEnabled(True)
            self.diarization_check.setChecked(True)
        else:
            # For non-SRT formats, diarization is always included and cannot be disabled
            self.diarization_check.setEnabled(False)
            self.diarization_check.setChecked(True)
            
        self.update_preview()
        
    def on_convention_changed(self, convention_text):
        if "Dresing" in convention_text:
            self.transcript_convention = "dresing_pehl"
        else:
            self.transcript_convention = "gat2"
        
        # Update diarization checkbox based on format and convention
        if self.export_format != "srt":
            # For non-SRT formats, diarization is always included
            self.diarization_check.setEnabled(False)
            self.diarization_check.setChecked(True)
                
        self.update_preview()
        
    def on_timestamp_changed(self, checked):
        self.current_include_timestamps = checked
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.update_preview)
        
    def update_preview(self):
        # Get the parent to regenerate transcript text
        parent = self.parent()
        
        if self.export_format == "srt":
            # For SRT format preview
            srt_text = parent.generate_srt_text(
                include_diarization=self.diarization_check.isChecked(),
                unassigned_handling="skip"  # Default for preview
            )
            self.preview_text.setPlainText(srt_text)
            return

        if self.export_format == "docx":
            # Show informative message for DOCX formats
            preview_text = "Preview not available for this format. The exported file will contain the full transcript with selected options."
            self.preview_text.setPlainText(preview_text)
            return

        # For other formats (HTML, TXT)
        if hasattr(parent, 'generate_transcript_text'):
            transcript_text = parent.generate_transcript_text(
                include_timestamps=self.current_include_timestamps,
                convention=self.transcript_convention,
                include_diarization=self.diarization_check.isChecked()
            )
            
            # Add project info if requested
            header_lines = []
            
            if self.title_check.isChecked() and self.project_info.get('name'):
                if self.export_format == "html":
                    escaped_name = parent.escape_html(self.project_info['name'])
                    header_lines.append(f"<h1>{escaped_name}</h1>")
                else:  # TXT
                    header_lines.append(self.project_info['name'])
                    header_lines.append("=" * len(self.project_info['name']))
                    header_lines.append("")
            
            if self.memo_check.isChecked() and self.project_info.get('memo'):
                if self.export_format == "html":
                    escaped_memo = parent.escape_html(self.project_info['memo'])
                    header_lines.append(f"<p><strong>Project Memo:</strong> {escaped_memo}</p>")
                else:  # TXT
                    header_lines.append(f"Project Memo: {self.project_info['memo']}")
                    header_lines.append("")
            
            if self.audio_check.isChecked() and self.audio_path:
                audio_name = Path(self.audio_path).name
                if self.export_format == "html":
                    escaped_audio = parent.escape_html(audio_name)
                    header_lines.append(f"<p><strong>Audio File:</strong> {escaped_audio}</p>")
                else:  # TXT
                    header_lines.append(f"Audio File: {audio_name}")
                    header_lines.append("")
            
            if header_lines:
                if self.export_format == "html":
                    header_text = "\n".join(header_lines)
                    escaped_transcript = parent.escape_html(transcript_text)
                    full_text = f"{header_text}\n{escaped_transcript}"
                else:  # TXT
                    header_text = "\n".join(header_lines)
                    full_text = f"{header_text}\n{transcript_text}"
            else:
                if self.export_format == "html":
                    full_text = parent.escape_html(transcript_text)
                else:
                    full_text = transcript_text
                    
        else:
            full_text = "Preview not available"
            
        if self.export_format == "html":
            # Choose font based on convention
            font_family = "'Courier New', monospace"
            if self.transcript_convention == "dresing_pehl":
                font_family = "'Times New Roman', serif"
            
            html_content = f"""
            <html>
            <head>
            <style>
            body {{
                font-family: {font_family};
                font-size: 10pt;
                line-height: 1.2;
                margin: 20px;
                white-space: pre;
            }}
            h1 {{
                font-family: Arial, sans-serif;
                color: #333;
                border-bottom: 2px solid #333;
                padding-bottom: 10px;
            }}
            </style>
            </head>
<body>
            {full_text}
            </body>
            </html>
            """
            self.preview_text.setHtml(html_content)
        else:
            self.preview_text.setPlainText(full_text)
    
    def get_export_settings(self):
        return {
            'format': self.export_format,
            'convention': self.transcript_convention,
            'include_timestamps': self.current_include_timestamps,
            'include_diarization': self.diarization_check.isChecked(),
            'include_title': self.title_check.isChecked(),
            'include_memo': self.memo_check.isChecked(),
            'include_audio': self.audio_check.isChecked()
        }

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

class SpeedKnob(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 1.0  # Default 1.0x speed
        self.min_value = 0.5
        self.max_value = 2.0
        self.step = 0.1
        self.is_dragging = False
        self.last_mouse_pos = None
        self.setMinimumSize(60, 60)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw knob background
        center = QPoint(self.width() // 2, self.height() // 2)
        radius = min(self.width(), self.height()) // 2 - 5
        
        # Outer circle
        painter.setBrush(QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawEllipse(center, radius, radius)
        
        # Value indicator
        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)
        
        indicator_length = radius - 5
        end_x = center.x() + indicator_length * math.cos(angle_rad)
        end_y = center.y() + indicator_length * math.sin(angle_rad)
        
        painter.setPen(QPen(QColor(0, 120, 215), 2))
        painter.drawLine(center, QPoint(int(end_x), int(end_y)))
        
        # Draw center dot
        painter.setBrush(QColor(0, 120, 215))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 4, 4)
        
        # Draw value text
        painter.setPen(QColor(50, 50, 50))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        value_text = f"{self.value:.1f}x"
        text_rect = QRect(center.x() - 30, center.y() - -2, 60, 20)
        painter.drawText(text_rect, Qt.AlignCenter, value_text)
        
        # Draw min/max labels
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(center.x() - 40, center.y() - radius + 50, "0.5x")
        painter.drawText(center.x() + 27, center.y() - radius + 50, "2.0x")
        
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
                            
    valueChanged = pyqtSignal(float)

class SRTEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.srt_blocks = []
        self.current_block_index = 0
        self.speakers = ["A", "B", "C", "D"]
        self.speaker_colors = [
            QColor(220, 240, 255),  # Light blue
            QColor(255, 220, 220),  # Light red
            QColor(220, 255, 220),  # Light green
            QColor(255, 255, 200)   # Light yellow
        ]
        self.context_blocks = 5
        self.current_file_path = None
        self.file_has_timestamps = True
        self.audio_file_path = None
        self.project_name = ""
        self.project_memo = ""
        self.text_display_font = QFont("Arial", 12)
        self.has_unsaved_changes = False
        self.current_theme = "light"
        self.playback_speed = 1.0
        self.segment_sync_buffer = 0
        self.original_audio_duration = 0
        
        # VLC audio player
        self.audio_player = None
        self.is_playing = False
        self.auto_sync_enabled = False
        self.auto_pause_enabled = False
        
        # Timer for UI updates
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.update_ui)
        self.ui_update_timer.start(50)
        
               # Check for VLC at startup
        self.vlc_available = self.check_vlc_available()
        
        if not self.vlc_available:
            # Show warning about missing VLC
            QMessageBox.warning(None, "VLC Not Found", 
                "VLC media player was not found on your system.\n\n"
                "For full functionality including playback speed control, please install VLC from:\n"
                "https://www.videolan.org/vlc/\n\n"
                "The application will use a basic fallback player without speed control.")
        
        self.init_ui()
        
    def check_vlc_available(self):
        """Check if VLC is installed and available"""
        try:
            # Try to create a VLC instance
            instance = vlc.Instance()
            # Try to create a player
            player = instance.media_player_new()
            # Release resources
            player.release()
            instance.release()
            return True
        except Exception as e:
            logger.warning(f"VLC not available: {e}")
            return False
        
    def init_ui(self):
        self.setWindowTitle("CapsGAT 1.3 - VLC Transcription Workstation")
        self.setGeometry(100, 100, 1400, 900)
        self.setWindowIcon(QIcon(resource_path('images/logo.ico')))
        
        # Create menu bar
        self.create_menu_bar()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        
        # Left panel - Context display
        left_panel = QVBoxLayout()
        
#         # VLC status indicator
#         self.vlc_status_label = QLabel()
#         self.update_vlc_status_display()
#         audio_layout.addWidget(self.vlc_status_label)
#         audio_layout.addWidget(self.audio_info_label)
        
        # Current block info display
        self.current_info_label = QLabel("No block selected")
        self.current_info_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                padding: 10px;
                border: 2px solid #ccc;
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
                background-color: #fafafa;
                border: 2px solid #ddd;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        left_panel.addWidget(self.text_display)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.btn_prev = QPushButton("← Previous (P)")
        self.btn_prev.clicked.connect(self.previous_block)
        
        self.lbl_current = QLabel("Current: -/-")
        
        self.btn_next = QPushButton("Next (N) →")
        self.btn_next.clicked.connect(self.next_block)
        
        self.btn_split = QPushButton("Split (Space)")
        self.btn_split.clicked.connect(self.split_current_block)
        
        self.btn_merge = QPushButton("Merge (Del)")
        self.btn_merge.clicked.connect(self.merge_with_next)
        
        self.btn_edit = QPushButton("Edit (E)")
        self.btn_edit.clicked.connect(self.edit_current_block)
        
        self.btn_unassign = QPushButton("Unassign (U)")
        self.btn_unassign.clicked.connect(self.unassign_current)
        
        self.btn_symbols = QPushButton("Symbols (*)")
        self.btn_symbols.clicked.connect(self.open_pause_dialog)
        
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_current)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_split)
        nav_layout.addWidget(self.btn_merge)
        nav_layout.addWidget(self.btn_edit)
        nav_layout.addWidget(self.btn_unassign)
        nav_layout.addWidget(self.btn_symbols)
        
        left_panel.addLayout(nav_layout)
        
        # Right panel - Controls
        right_panel = QVBoxLayout()
        
        # Speaker assignment
        speaker_label = QLabel("Assign Speaker:")
        speaker_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(speaker_label)
        
        self.speaker_container = QWidget()
        self.speaker_layout = QVBoxLayout(self.speaker_container)
        self.create_speaker_widgets()
        right_panel.addWidget(self.speaker_container)
        
        # Manage speakers
        manage_layout = QHBoxLayout()
        self.speaker_edit = QSpinBox()
        self.speaker_edit.setMinimum(2)
        self.speaker_edit.setMaximum(8)
        self.speaker_edit.setValue(4)
        self.speaker_edit.valueChanged.connect(self.update_speaker_count)
        
        manage_layout.addStretch()
        manage_layout.addWidget(QLabel("Number of speakers:"))
        manage_layout.addWidget(self.speaker_edit)
        manage_layout.addStretch()
        right_panel.addLayout(manage_layout)
        
        # Audio Controls Label
        audio_label = QLabel("Audio Controls:")
        audio_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(audio_label)

        # Audio controls group
        audio_group = QGroupBox()
        audio_layout = QVBoxLayout()

        # Audio file info
        self.audio_info_label = QLabel("No audio loaded")
        self.audio_info_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0; 
                padding: 5px; 
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
        audio_layout.addWidget(self.audio_progress)

        # Time display
        time_layout = QHBoxLayout()
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        
        self.btn_jump_to = QPushButton("Jump (Ctrl+J)")
        self.btn_jump_to.clicked.connect(self.jump_to_time)
        self.btn_jump_to.setEnabled(False)
        
        time_layout.addWidget(self.time_label)
        time_layout.addWidget(self.btn_jump_to)
        audio_layout.addLayout(time_layout)

        # Audio controls
        audio_controls_layout = QHBoxLayout()
        
        audio_button_font = QFont("Segoe UI Symbol")
        


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
        audio_controls_layout.addStretch()

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
        speed_layout.addWidget(QLabel("Playback Speed:"))
        
        self.speed_slower_btn = QPushButton("-")
        self.speed_slower_btn.clicked.connect(lambda: self.speed_knob.set_value_direct(max(0.5, self.playback_speed - 0.1)))
        self.speed_slower_btn.setFixedWidth(30)
        speed_layout.addWidget(self.speed_slower_btn)
        
        self.speed_knob = SpeedKnob()
        self.speed_knob.valueChanged.connect(self.change_playback_speed)
        speed_layout.addWidget(self.speed_knob)
        
        # Disable speed controls if VLC is not available
        if not self.vlc_available:
            self.speed_knob.setEnabled(False)
            self.speed_slower_btn.setEnabled(False)
            self.speed_normal_btn.setEnabled(False)
            self.speed_faster_btn.setEnabled(False)
            self.speed_knob.setToolTip("Speed control requires VLC media player")
            self.speed_slower_btn.setToolTip("Speed control requires VLC media player")
            self.speed_normal_btn.setToolTip("Speed control requires VLC media player")
            self.speed_faster_btn.setToolTip("Speed control requires VLC media player")
                     

        
        self.speed_normal_btn = QPushButton("Reset")
        self.speed_normal_btn.clicked.connect(lambda: self.speed_knob.set_value_direct(1.0))
        self.speed_normal_btn.setFixedWidth(50)
        
        self.speed_faster_btn = QPushButton("+")
        self.speed_faster_btn.clicked.connect(lambda: self.speed_knob.set_value_direct(min(2.0, self.playback_speed + 0.1)))
        self.speed_faster_btn.setFixedWidth(30)
        
        speed_layout.addWidget(self.speed_faster_btn)
        speed_layout.addWidget(self.speed_normal_btn)
        
        
        audio_layout.addLayout(speed_layout)

        audio_group.setLayout(audio_layout)
        right_panel.addWidget(audio_group)
        
        # Unassigned blocks
        unassigned_blocks_label = QLabel("Unassigned Blocks:")
        unassigned_blocks_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(unassigned_blocks_label)
        self.unassigned_list = QListWidget()
        self.unassigned_list.itemDoubleClicked.connect(self.jump_to_block)
        right_panel.addWidget(self.unassigned_list)
        
        # Symbols section
        symbols_label = QLabel("GAT2 Symbols:")
        symbols_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_panel.addWidget(symbols_label)
        
        self.btn_open_symbols = QPushButton("Open Symbols Dialog (* key)")
        self.btn_open_symbols.clicked.connect(self.open_pause_dialog)
        self.btn_open_symbols.setStyleSheet("""
            QPushButton {
                background-color: #e0e0ff;
                padding: 10px;
                font-weight: bold;
                border: 2px solid #aaa;
                border-radius: 5px;
            }
        """)
        right_panel.addWidget(self.btn_open_symbols)
                
        right_panel.addStretch()
        
        layout.addLayout(left_panel, 4)
        layout.addLayout(right_panel, 1)
        
        self.setup_shortcuts()
    
    def create_menu_bar(self):
        # [Menu bar creation remains the same]
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
        export_action.triggered.connect(self.export_transcript)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu('Edit')
        
        search_action = QAction('Search...', self)
        search_action.triggered.connect(self.open_search_dialog)
        edit_menu.addAction(search_action)
        
        settings_action = QAction('Settings...', self)
        settings_action.triggered.connect(self.open_settings)
        edit_menu.addAction(settings_action)
        
        project_memo_action = QAction('Project Memo...', self)
        project_memo_action.triggered.connect(self.open_project_memo)
        edit_menu.addAction(project_memo_action)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        shortcuts_action = QAction('Shortcuts', self)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        manual_action = QAction('Online Manual', self)
        manual_action.triggered.connect(self.open_manual)
        help_menu.addAction(manual_action)
        
        about_action = QAction('About CapsGAT', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_shortcuts(self):
        # [Shortcuts remain the same]
        for i in range(len(self.speakers)):
            QShortcut(QKeySequence(str(i+1)), self).activated.connect(
                lambda idx=i: self.assign_speaker(idx))
        QShortcut(QKeySequence("N"), self).activated.connect(self.next_block)
        QShortcut(QKeySequence("P"), self).activated.connect(self.previous_block)
        QShortcut(QKeySequence("Right"), self).activated.connect(self.next_block)
        QShortcut(QKeySequence("Left"), self).activated.connect(self.previous_block)
        QShortcut(QKeySequence("Space"), self).activated.connect(self.split_current_block)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self.merge_with_next)
        QShortcut(QKeySequence("E"), self).activated.connect(self.edit_current_block)
        QShortcut(QKeySequence("*"), self).activated.connect(self.open_pause_dialog)
        QShortcut(QKeySequence("U"), self).activated.connect(self.unassign_current)
        QShortcut(QKeySequence("Return"), self).activated.connect(self.insert_empty_line)
        QShortcut(QKeySequence("."), self).activated.connect(lambda: self.handle_pause("(.)"))
        QShortcut(QKeySequence("H"), self).activated.connect(lambda: self.handle_pause("°h"))
        QShortcut(QKeySequence("Shift+H"), self).activated.connect(lambda: self.handle_pause("h°"))
        
        QShortcut(QKeySequence("PgUp"), self).activated.connect(self.rewind_audio)
        QShortcut(QKeySequence("End"), self).activated.connect(self.toggle_playback)
        QShortcut(QKeySequence("PgDown"), self).activated.connect(self.forward_audio)
        QShortcut(QKeySequence("Ctrl+J"), self).activated.connect(self.jump_to_time)
               
        QShortcut(QKeySequence("+"), self).activated.connect(lambda: self.speed_knob.set_value_direct(min(2.0, self.playback_speed + 0.1)))
        QShortcut(QKeySequence("-"), self).activated.connect(lambda: self.speed_knob.set_value_direct(max(0.5, self.playback_speed - 0.1)))
        QShortcut(QKeySequence("0"), self).activated.connect(lambda: self.speed_knob.set_value_direct(1.0))
        
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.open_search_dialog)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.find_next)
        QShortcut(QKeySequence("Shift+F3"), self).activated.connect(self.find_previous)
    
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
                self.time_label.setText(f"{current_str} / {duration_str}{speed_str}")
                
                # Auto-sync if enabled
                if self.auto_sync_enabled and self.srt_blocks and self.file_has_timestamps:
                    self.auto_sync_with_audio(current_time)
    
    def load_audio_file(self):
        """Load an audio file using appropriate player"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Audio File", "", 
            "Audio Files (*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma);;All Files (*)"
        )
        
        if file_path:
            # Check for subtitle files
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
            
            # Reset to 1.0x speed for initial load
            self.playback_speed = 1.0
            self.speed_knob.value = 1.0
            self.speed_knob.update()
            self.speed_normal_btn.setText("1.0x")
            
            # Choose player based on VLC availability
            if self.vlc_available:
                # Use VLC player
                self.audio_player = VlcAudioPlayer()
                player_name = "VLC"
            else:
                # Use fallback player
                if HAS_PYAUDIO:
                    self.audio_player = SimpleAudioPlayer()
                    player_name = "Simple"
                else:
                    QMessageBox.warning(self, "No Audio Backend", 
                        "Neither VLC nor PyAudio is available on your system.\n\n"
                        "Please install VLC from https://www.videolan.org/vlc/\n"
                        "or install PyAudio with: pip install pyaudio")
                    return
            
            # Connect signals
            if self.audio_player:
                self.audio_player.playback_started.connect(self.on_playback_started)
                self.audio_player.playback_stopped.connect(self.on_playback_stopped)
                self.audio_player.position_changed.connect(self.on_position_changed)
                
                if hasattr(self.audio_player, 'playback_paused'):
                    self.audio_player.playback_paused.connect(self.on_playback_paused)
                if hasattr(self.audio_player, 'end_reached'):
                    self.audio_player.end_reached.connect(self.on_playback_ended)
                
                if self.audio_player.load_file(file_path):
                    self.audio_file_path = file_path
                    audio_name = Path(file_path).name
                    
                    # Update status
                    if self.vlc_available:
                        status = f"Audio loaded: {audio_name}"
                    else:
                        status = f"Audio loaded: {audio_name} (⚠ No VLC player found - using fallback)"
                    
                    self.audio_info_label.setText(status)
                    
                    # Enable controls
                    self.btn_play.setEnabled(True)
                    self.btn_rewind.setEnabled(True)
                    self.btn_forward.setEnabled(True)
                    self.btn_jump_to.setEnabled(True)
                    self.auto_sync_check.setEnabled(self.file_has_timestamps)
                    self.auto_pause_check.setEnabled(True)
                    self.audio_progress.setEnabled(True)
                    
                    logger.info(f"Audio loaded with {player_name} player: {audio_name}")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to load audio file")
                    self.audio_player = None
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
    
    def change_playback_speed(self, new_speed):
        """Change playback speed (only works with VLC)"""
        if not self.vlc_available:
            # Show message that speed control requires VLC
            QMessageBox.information(self, "Speed Control Not Available",
                "Playback speed control requires VLC media player.\n\n"
                "Please install VLC from https://www.videolan.org/vlc/")
            return
        
        new_speed = max(0.5, min(2.0, new_speed))
        
        # Don't process if speed hasn't changed
        if abs(new_speed - self.playback_speed) < 0.01:
            return
        
        self.playback_speed = new_speed
        
        if self.audio_player and isinstance(self.audio_player, VlcAudioPlayer):
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
        """Handle position change"""
        # This is handled in update_ui
        pass
    
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
                start_ms = self.time_to_ms(block['start_time'])
                end_ms = self.time_to_ms(block['end_time'])
                
                if start_ms - buffer_ms <= current_time_ms <= end_ms + buffer_ms:
                    return  # Still in current block
        
        # Search for matching block
        for i, block in enumerate(self.srt_blocks):
            if block.get('start_time') and block.get('end_time'):
                start_ms = self.time_to_ms(block['start_time'])
                end_ms = self.time_to_ms(block['end_time'])
                
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
    
    def toggle_auto_pause(self, checked):
        """Toggle auto-pause"""
        self.auto_pause_enabled = checked
        logger.info(f"Auto-pause {'enabled' if checked else 'disabled'}")

    def escape_html(self, text):
        """Escape HTML special characters to prevent interpretation as HTML tags"""
        if not text:
            return text
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))
    
    def new_project(self):
        """Create new project"""
        if self.check_unsaved_changes():
            self.srt_blocks = []
            self.current_block_index = 0
            self.current_file_path = None
            self.project_name = ""
            self.project_memo = ""
            self.has_unsaved_changes = False
            
            self.speakers = ["A", "B", "C", "D"]
            self.speaker_edit.setValue(4)
            
            # Stop audio
            if self.audio_player:
                self.audio_player.cleanup()
                self.audio_player = None
            
            self.audio_file_path = None
            self.audio_info_label.setText("No audio loaded")
            self.btn_play.setEnabled(False)
            self.btn_rewind.setEnabled(False)
            self.btn_forward.setEnabled(False)
            self.btn_jump_to.setEnabled(False)
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
            self.create_speaker_widgets()
            self.setup_shortcuts()
            
            self.update_display()
            self.clear_unsaved_changes()
            
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
        
        # Find the position of this block in the displayed text
        start_idx = max(0, self.current_block_index - self.context_blocks)
        display_block_pos = (block_idx - start_idx) * 2
        
        # Calculate the position in the displayed text
        cursor.movePosition(cursor.Start)
        for i in range(display_block_pos):
            cursor.movePosition(cursor.Down)
            
        # Move to the beginning of the block text (after prefix)
        cursor.movePosition(cursor.Down)
        cursor.movePosition(cursor.StartOfLine)
        
        # Skip the prefix (">> " or "   ")
        cursor.movePosition(cursor.Right, cursor.MoveAnchor, 3)
        
        # Move to the start position within the text
        cursor.movePosition(cursor.Right, cursor.MoveAnchor, start_pos)
        cursor.movePosition(cursor.Right, cursor.KeepAnchor, end_pos - start_pos)
        
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
• 1-4: Assign speakers A-D
• U: Unassign current block

Editing:
• Space: Split current block
• Delete: Merge with next block
• E: Edit block content
• Enter: Insert empty line

GAT2 Symbols:
• *: Open symbols dialog
• .: Insert micropause (with placement)
• h: Insert short inhale (with placement)
• H: Insert short exhale (with placement)

Audio Controls:
• End: Play/Pause audio
• PgUp: Rewind 5 seconds
• PgDn: Fast forward 5 seconds
• Ctrl+J: Jump to Time
• -: Lower Playback Speed
• +: Speed up Playback

Search Functions:
• Ctrl+F: Open search dialog
• F3: Find Next
• Shift+F3: Find Previous

File Operations:
• Ctrl+N: New Project
• Ctrl+O: Open Project
• Ctrl+S: Save Project
"""
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)
        
    def open_manual(self):
        """Open online manual in browser"""
        webbrowser.open("https://github.com/anouarg88/CapsGAT/wiki")
        
    def show_about(self):
        """Show about dialog"""
        about_text = """
<b style="font-size: 16px;">CapsGAT 1.3</b><br><br>

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
Engineered wtih DeepSeek V3.2

"""
        QMessageBox.about(self, "About CapsGAT", about_text)
        
    def mark_unsaved_changes(self):
        """Mark that there are unsaved changes"""
        self.has_unsaved_changes = True
        base_title = "CapsGAT 1.3 - Streaming Transcription Workstation"
        if self.project_name:
            self.setWindowTitle(f"{base_title} - {self.project_name} *")
        else:
            self.setWindowTitle(f"{base_title} *")
            
    def clear_unsaved_changes(self):
        """Clear unsaved changes marker"""
        self.has_unsaved_changes = False
        base_title = "CapsGAT 1.3 - Streaming Transcription Workstation"
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
        
    def open_settings(self):
        dialog = SettingsDialog(self.text_display_font, self.current_theme, self)
        if dialog.exec_() == QDialog.Accepted:
            self.text_display_font = dialog.get_font()
            self.text_display.setFont(self.text_display_font)
            theme = dialog.get_theme()
            self.apply_viewer_theme(theme)
            
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
     
    def load_file_from_path(self, file_path):
        """Load a subtitle file from given path"""
        try:
            file_extension = Path(file_path).suffix.lower()
            
            if file_extension == '.srt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.srt_blocks = self.parse_srt(content)
                self.file_has_timestamps = True
                
            elif file_extension == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.srt_blocks = self.parse_text(content)
                self.file_has_timestamps = False
                
            elif file_extension == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                self.srt_blocks = self.parse_json(content)
                self.file_has_timestamps = any(block.get('start_time') for block in self.srt_blocks)
                
            elif file_extension == '.tsv':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.srt_blocks = self.parse_tsv(content)
                self.file_has_timestamps = True
            
            self.current_block_index = 0
            self.current_file_path = file_path
            
            # Only enable auto-sync checkbox if we have timestamps AND audio is loaded
            self.auto_sync_check.setEnabled(self.file_has_timestamps and self.audio_file_path is not None)
            # Auto-pause is always enabled when audio is loaded
            self.auto_pause_check.setEnabled(self.audio_file_path is not None)
            
            # Ensure checkboxes reflect the actual state
            self.auto_sync_check.setChecked(self.auto_sync_enabled)
            self.auto_pause_check.setChecked(self.auto_pause_enabled)
            
            self.update_display()
            self.mark_unsaved_changes()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load file: {str(e)}")

    def create_speaker_widgets(self):
        for i in reversed(range(self.speaker_layout.count())): 
            self.speaker_layout.itemAt(i).widget().setParent(None)
        
        self.speaker_layout.setSpacing(5)
        self.speaker_layout.setContentsMargins(0, 0, 0, 0)
        
        self.speaker_widgets = []
        for i, speaker in enumerate(self.speakers):
            speaker_widget = QWidget()
            speaker_layout = QHBoxLayout(speaker_widget)
            speaker_layout.setSpacing(10)
            speaker_layout.setContentsMargins(5, 2, 5, 2)
            
            color_label = QLabel("■")
            color_label.setStyleSheet(f"color: {self.speaker_colors[i].name()}; font-size: 20px;")
            
            speaker_name_edit = QLineEdit(speaker)
            speaker_name_edit.textChanged.connect(lambda text, idx=i: self.rename_speaker(idx, text))
            speaker_name_edit.setFixedWidth(120)
            
            speaker_btn = QPushButton(f"{i+1}. Assign")
            speaker_btn.clicked.connect(lambda checked, idx=i: self.assign_speaker(idx))
            
            if self.current_theme == "dark":
                speaker_btn.setStyleSheet(f"""
                    QPushButton {{ 
                        background-color: {self.speaker_colors[i].name()}; 
                        color: white;
                        border: 2px solid #676767;
                        padding: 3px 5px;
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
                        border: 2px solid darkgray;
                        padding: 3px 5px;
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
            centered_widget.setMinimumHeight(40)
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
        
    def rename_speaker(self, speaker_idx, new_name):
        if speaker_idx < len(self.speakers):
            self.speakers[speaker_idx] = new_name
            self.update_display()
            self.mark_unsaved_changes()
        
    def update_speaker_count(self, count):
        while len(self.speakers) > count:
            self.speakers.pop()
            self.speaker_colors.pop()
        while len(self.speakers) < count:
            new_idx = len(self.speakers)
            self.speakers.append(chr(65 + new_idx))
            self.speaker_colors.append(QColor(200, 200, 200))
        
        self.create_speaker_widgets()
        self.setup_shortcuts()
        self.update_display()
        self.mark_unsaved_changes()
        
    def load_file(self):
        if not self.check_unsaved_changes():
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", 
            "All Supported Files (*.srt *.txt *.json *.tsv);;SRT Files (*.srt);;Text Files (*.txt);;JSON Files (*.json);;TSV Files (*.tsv)"
        )
        if file_path:
            self.load_file_from_path(file_path)
    
    def parse_srt(self, content):
        blocks = []
        srt_blocks = content.strip().split('\n\n')
        
        for block in srt_blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    index = int(lines[0].strip())
                    time_line = lines[1].strip()
                    # Fixed regex to properly capture milliseconds
                    time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                    
                    if time_match:
                        text = '\n'.join(lines[2:]).strip()
                        # Include milliseconds in the time string
                        block_data = {
                            'index': index,
                            'start_time': f"{time_match.group(1)}:{time_match.group(2)}:{time_match.group(3)},{time_match.group(4)}",
                            'start_ms': int(time_match.group(4)),
                            'end_time': f"{time_match.group(5)}:{time_match.group(6)}:{time_match.group(7)},{time_match.group(8)}",
                            'end_ms': int(time_match.group(8)),
                            'text': text,
                            'speaker': None,
                            'is_turn_start': True
                        }
                        blocks.append(block_data)
                except ValueError:
                    continue
        
        return blocks
    
    def parse_text(self, content):
        blocks = []
        lines = content.strip().split('\n')
        
        for i, line in enumerate(lines):
            if line.strip():
                block_data = {
                    'index': i + 1,
                    'start_time': '',
                    'end_time': '',
                    'text': line.strip(),
                    'speaker': None,
                    'is_turn_start': True
                }
                blocks.append(block_data)
        
        return blocks
    
    def parse_tsv(self, content):
        """Parse TSV file with start, end, and text columns"""
        blocks = []
        lines = content.strip().split('\n')
        
        for i, line in enumerate(lines):
            if i == 0:  # Skip header
                continue
                
            parts = line.split('\t')
            if len(parts) >= 3:
                start_ms = int(parts[0])
                end_ms = int(parts[1])
                text = parts[2]
                
                start_time = self.ms_to_srt_time(start_ms)
                end_time = self.ms_to_srt_time(end_ms)
                
                block_data = {
                    'index': i,
                    'start_time': start_time,
                    'end_time': end_time,
                    'text': text,
                    'speaker': None,
                    'is_turn_start': True
                }
                blocks.append(block_data)
        
        return blocks
    
    def ms_to_srt_time(self, ms):
        """Convert milliseconds to SRT time format (HH:MM:SS,mmm)"""
        hours = ms // 3600000
        ms %= 3600000
        minutes = ms // 60000
        ms %= 60000
        seconds = ms // 1000
        milliseconds = ms % 1000
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def auto_segment_tokens(self, tokens, timestamps):
        """Auto-segment tokens based on pause detection"""
        if len(tokens) != len(timestamps) or len(tokens) < 2:
            return [{'text': ''.join(tokens), 'start_time': '', 'end_time': ''}]
        
        gaps = []
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i-1]
            gaps.append(gap)
        
        avg_gap = sum(gaps) / len(gaps)
        threshold = avg_gap * 2.5
        
        segments = []
        current_segment = []
        current_start = timestamps[0]
        
        for i, (token, timestamp) in enumerate(zip(tokens, timestamps)):
            current_segment.append(token)
            
            if i < len(timestamps) - 1:
                gap = timestamps[i+1] - timestamp
                if gap > threshold:
                    segment_text = ''.join(current_segment)
                    segments.append({
                        'text': segment_text,
                        'start_time': self.seconds_to_srt_time(current_start),
                        'end_time': self.seconds_to_srt_time(timestamp + gap/2)
                    })
                    current_segment = []
                    if i < len(timestamps) - 1:
                        current_start = timestamps[i+1]
        
        if current_segment:
            segment_text = ''.join(current_segment)
            segments.append({
                'text': segment_text,
                'start_time': self.seconds_to_srt_time(current_start),
                'end_time': self.seconds_to_srt_time(timestamps[-1] + avg_gap)
            })
        
        return segments
    
    def seconds_to_srt_time(self, seconds):
        """Convert seconds to SRT time format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        milliseconds = int((secs - int(secs)) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{int(secs):02d},{milliseconds:03d}"
    
    def parse_json(self, content):
        blocks = []
        
        try:
            if isinstance(content, dict) and 'tokens' in content and 'timestamps' in content:
                tokens = content['tokens']
                timestamps = content['timestamps']
                
                dialog = JsonImportDialog(has_tokens=True, parent=self)
                if dialog.exec_() == QDialog.Accepted:
                    option = dialog.get_import_option()
                    
                    if option == "one_block":
                        text = ''.join(tokens) if tokens else ""
                        block_data = {
                            'index': 1,
                            'start_time': '',
                            'end_time': '',
                            'text': text,
                            'speaker': None,
                            'is_turn_start': True
                        }
                        blocks.append(block_data)
                        
                    elif option == "tokens":
                        for i, (token, timestamp) in enumerate(zip(tokens, timestamps)):
                            block_data = {
                                'index': i + 1,
                                'start_time': self.seconds_to_srt_time(timestamp),
                                'end_time': '',
                                'text': token,
                                'speaker': None,
                                'is_turn_start': True
                            }
                            blocks.append(block_data)
                            
                    elif option == "auto_segment":
                        segments = self.auto_segment_tokens(tokens, timestamps)
                        for i, segment in enumerate(segments):
                            block_data = {
                                'index': i + 1,
                                'start_time': segment['start_time'],
                                'end_time': segment['end_time'],
                                'text': segment['text'],
                                'speaker': None,
                                'is_turn_start': True
                            }
                            blocks.append(block_data)
                else:
                    return []
                
            elif isinstance(content, dict) and 'segments' in content:
                segments = content['segments']
                for i, segment in enumerate(segments):
                    block_data = {
                        'index': i + 1,
                        'start_time': self.seconds_to_srt_time(segment.get('start', 0)),
                        'end_time': self.seconds_to_srt_time(segment.get('end', 0)),
                        'text': segment.get('text', '').strip(),
                        'speaker': None,
                        'is_turn_start': True
                    }
                    blocks.append(block_data)
                    
            elif isinstance(content, dict) and 'text' in content:
                block_data = {
                    'index': 1,
                    'start_time': '',
                    'end_time': '',
                    'text': content['text'].strip(),
                    'speaker': None,
                    'is_turn_start': True
                }
                blocks.append(block_data)
                
            elif isinstance(content, list):
                for i, item in enumerate(content):
                    if isinstance(item, dict):
                        block_data = {
                            'index': i + 1,
                            'start_time': item.get('start_time', ''),
                            'end_time': item.get('end_time', ''),
                            'text': item.get('text', ''),
                            'speaker': None,
                            'is_turn_start': True
                        }
                        blocks.append(block_data)
            elif isinstance(content, dict):
                transcript_data = content.get('transcript', content.get('blocks', []))
                if isinstance(transcript_data, list):
                    for i, item in enumerate(transcript_data):
                        if isinstance(item, dict):
                            block_data = {
                                'index': i + 1,
                                'start_time': item.get('start_time', ''),
                                'end_time': item.get('end_time', ''),
                                'text': item.get('text', ''),
                                'speaker': None,
                                'is_turn_start': True
                            }
                            blocks.append(block_data)
            
            if not blocks:
                QMessageBox.warning(self, "JSON Format", 
                                   "The JSON file doesn't contain recognizable transcript data.")
                
        except Exception as e:
            QMessageBox.critical(self, "JSON Error", 
                               f"Could not parse JSON file: {str(e)}")
        
        return blocks
    
    def save_project(self, force_save_as=False):
        if not self.srt_blocks:
            return
            
        file_path = None
        
        if not force_save_as and self.current_file_path:
            if self.current_file_path.endswith('.capsgat'):
                file_path = self.current_file_path
            else:
                force_save_as = True
        
        if force_save_as or not file_path:
            default_name = ""
            if self.project_name:
                default_name = self.project_name.replace(" ", "_") + ".capsgat"
            elif self.current_file_path:
                original_stem = Path(self.current_file_path).stem
                default_name = f"{original_stem}.capsgat"
            else:
                default_name = "transcript_project.capsgat"
                
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Save Project As", 
                default_name,
                "CapsGAT Project Files (*.capsgat)"
            )
            
            if not file_path:
                return
                
            if not file_path.endswith('.capsgat'):
                file_path += '.capsgat'
        
        if file_path:
            try:
                project_data = {
                    'srt_blocks': self.srt_blocks,
                    'current_block_index': self.current_block_index,
                    'speakers': self.speakers,
                    'source_file': self.current_file_path,
                    'file_has_timestamps': self.file_has_timestamps,
                    'audio_file_path': self.audio_file_path,
                    'project_name': self.project_name,
                    'project_memo': self.project_memo,
                    'text_display_font': {
                        'family': self.text_display_font.family(),
                        'size': self.text_display_font.pointSize()
                    },
                    'viewer_theme': self.current_theme,
                    'playback_speed': self.playback_speed
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=2, ensure_ascii=False)
                    
                self.current_file_path = file_path
                self.clear_unsaved_changes()
                QMessageBox.information(self, "Success", f"Project saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save project: {str(e)}")
    
    def load_project(self):
        if not self.check_unsaved_changes():
            return
            
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "CapsGAT Project Files (*.capsgat)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                
                self.srt_blocks = project_data['srt_blocks']
                self.current_block_index = project_data['current_block_index']
                self.speakers = project_data['speakers']
                self.current_file_path = project_data.get('source_file', '')
                self.file_has_timestamps = project_data.get('file_has_timestamps', True)
                self.project_name = project_data.get('project_name', '')
                self.project_memo = project_data.get('project_memo', '')
                self.playback_speed = project_data.get('playback_speed', 1.0)
                
                font_data = project_data.get('text_display_font')
                if font_data:
                    self.text_display_font = QFont(font_data['family'], font_data['size'])
                    self.text_display.setFont(self.text_display_font)
                
                audio_path = project_data.get('audio_file_path')
                if audio_path and Path(audio_path).exists():
                    self.audio_file_path = audio_path
                    # Get original duration
                    try:
                        info = sf.info(audio_path)
                        self.original_audio_duration = info.duration
                    except:
                        self.original_audio_duration = 0
                    
                    # Load audio at saved speed
                    self.load_audio_file_for_project(audio_path, self.playback_speed)
                    
                viewer_theme = project_data.get('viewer_theme', 'light')
                self.apply_viewer_theme(viewer_theme)
                
                # Update speed display
                self.speed_knob.value = self.playback_speed
                self.speed_knob.update()
                
                self.update_display()
                self.clear_unsaved_changes()
                
                QMessageBox.information(self, "Success", f"Project loaded from {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load project: {str(e)}")

    def load_audio_file_for_project(self, audio_path, speed):
        """Load audio file for a project (without showing file dialog)"""
        # Stop any existing audio
        if self.audio_player:
            self.audio_player.cleanup()
            self.audio_player = None
        
        # Create new streaming player
        self.audio_player = StreamingAudioPlayer()
        self.audio_player.playback_started.connect(self.on_playback_started)
        self.audio_player.playback_stopped.connect(self.on_playback_stopped)
        self.audio_player.position_changed.connect(self.on_position_changed)
        
        try:
            # Get original duration
            info = sf.info(audio_path)
            self.original_audio_duration = info.duration
            
            # Load audio file at project speed
            self.audio_player.load_file(audio_path, speed)
            self.audio_file_path = audio_path
            
            # Update UI
            audio_name = Path(audio_path).name
            self.audio_info_label.setText(f"Audio: {audio_name}")
            
            # Enable controls
            self.btn_play.setEnabled(True)
            self.btn_rewind.setEnabled(True)
            self.btn_forward.setEnabled(True)
            self.btn_jump_to.setEnabled(True)
            self.auto_sync_check.setEnabled(self.file_has_timestamps)
            self.auto_pause_check.setEnabled(True)
            self.audio_progress.setEnabled(True)
            
            logger.info(f"Audio loaded for project at {speed:.1f}x speed: {audio_name}")
            
        except Exception as e:
            logger.error(f"Failed to load audio for project: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load audio: {str(e)}")
            self.audio_player = None

    def apply_viewer_theme(self, theme):
        self.current_theme = theme
        if theme == "dark":
            self.text_display.setStyleSheet("""
                QTextEdit {
                    background-color: #2b2b2b;
                    color: #ffffff;
                    border: 2px solid #555;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
            self.current_info_label.setStyleSheet("""
                QLabel {
                    background-color: #3a3a3a;
                    color: #ffffff;
                    padding: 10px;
                    border: 2px solid #555;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            self.speaker_colors = [
                QColor(60, 80, 100),
                QColor(100, 60, 60),
                QColor(60, 100, 60),
                QColor(100, 100, 60)
            ]
        else:
            self.text_display.setStyleSheet("""
                QTextEdit {
                    background-color: #fafafa;
                    color: #000000;
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
            self.current_info_label.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    color: #000000;
                    padding: 10px;
                    border: 2px solid #ccc;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
            self.speaker_colors = [
                QColor(220, 240, 255),
                QColor(255, 220, 220),
                QColor(220, 255, 220),
                QColor(255, 255, 200)
            ]
        
        self.create_speaker_widgets()
        self.update_display()
    
    def update_display(self):
        if not self.srt_blocks:
            self.text_display.setPlainText("No content loaded")
            self.current_info_label.setText("No block selected")
            self.lbl_current.setText("Current: -/-")
            return
        
        current_block = self.srt_blocks[self.current_block_index]
        speaker_name = self.speakers[current_block['speaker']] if current_block['speaker'] is not None else "UNASSIGNED"
        turn_indicator = " [TURN START]" if current_block.get('is_turn_start', True) else " [CONTINUATION]"
        self.current_info_label.setText(
            f"Block {current_block['index']} | Speaker: {speaker_name}{turn_indicator} | "
            f"Time: {current_block['start_time']} --> {current_block['end_time']}"
        )
        
        start_idx = max(0, self.current_block_index - self.context_blocks)
        end_idx = min(len(self.srt_blocks), self.current_block_index + self.context_blocks + 1)
        
        display_text = ""
        for i in range(start_idx, end_idx):
            block = self.srt_blocks[i]
            
            if i == self.current_block_index:
                display_text += f">> {block['text']}\n\n"
            else:
                display_text += f"   {block['text']}\n\n"
        
        self.text_display.setPlainText(display_text)
        
        self.colorize_display()
        
        self.lbl_current.setText(f"Current: {self.current_block_index + 1}/{len(self.srt_blocks)}")
        
        self.unassigned_list.clear()
        for i, block in enumerate(self.srt_blocks):
            if block['speaker'] is None:
                preview = block['text'][:50] + "..." if len(block['text']) > 50 else block['text']
                self.unassigned_list.addItem(f"{i+1}: {preview}")
    
    def colorize_display(self):
        cursor = self.text_display.textCursor()
        cursor.select(cursor.Document)
        
        format_normal = QTextCharFormat()
        cursor.setCharFormat(format_normal)
        
        start_idx = max(0, self.current_block_index - self.context_blocks)
        
        for i in range(start_idx, min(len(self.srt_blocks), self.current_block_index + self.context_blocks + 1)):
            block = self.srt_blocks[i]
            if block['speaker'] is not None and block['speaker'] < len(self.speaker_colors):
                color = self.speaker_colors[block['speaker']]
                
                block_pos = (i - start_idx) * 2
                
                cursor.movePosition(cursor.Start)
                for _ in range(block_pos):
                    cursor.movePosition(cursor.Down)
                
                cursor.movePosition(cursor.Down, cursor.KeepAnchor)
                
                block_format = QTextCharFormat()
                block_format.setBackground(color)
                cursor.setCharFormat(block_format)
        
        current_pos = (self.current_block_index - start_idx) * 2
        cursor.movePosition(cursor.Start)
        for _ in range(current_pos):
            cursor.movePosition(cursor.Down)
        
        cursor.movePosition(cursor.Down, cursor.KeepAnchor)
        current_format = QTextCharFormat()
        if self.current_theme == "dark":
            current_format.setBackground(QColor(120, 120, 200))
        else:
            current_format.setBackground(QColor(255, 240, 200))
        current_format.setFontWeight(QFont.Bold)
        cursor.setCharFormat(current_format)
        
        self.scroll_to_current_block()
    
    def scroll_to_current_block(self):
        cursor = self.text_display.textCursor()
        cursor.movePosition(cursor.Start)
        
        start_idx = max(0, self.current_block_index - self.context_blocks)
        blocks_before_current = self.current_block_index - start_idx
        
        for _ in range(blocks_before_current * 2):
            cursor.movePosition(cursor.Down)
        
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
        
        if not (self.is_playing and self.auto_sync_enabled):
            self.find_next_unassigned()
            
        self.mark_unsaved_changes()
        
    def unassign_current(self):
        if not self.srt_blocks:
            return
            
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
        dialog = BlockSplitDialog(current_block['text'], self)
        
        if dialog.exec_() == QDialog.Accepted:
            split_pos = dialog.split_position
            if 0 < split_pos < len(current_block['text']):
                text_before = current_block['text'][:split_pos].strip()
                text_after = current_block['text'][split_pos:].strip()
                
                if text_before and text_after:
                    if current_block.get('start_time') and current_block.get('end_time'):
                        original_end_time = current_block['end_time']
                        original_end_ms = self.time_to_ms(original_end_time)
                        
                        start_ms = self.time_to_ms(current_block['start_time'])
                        end_ms = original_end_ms
                        total_duration = end_ms - start_ms
                        
                        total_chars = len(text_before) + len(text_after)
                        before_proportion = len(text_before) / total_chars

                        split_ms = start_ms + int(total_duration * before_proportion)
                        split_ms = max(start_ms + 100, min(end_ms - 100, split_ms))

                        current_block['text'] = text_before
                        current_block['end_time'] = self.ms_to_time(split_ms)

                        new_block = current_block.copy()
                        new_block['text'] = text_after
                        new_block['index'] = max(block['index'] for block in self.srt_blocks) + 1
                        new_block['start_time'] = self.ms_to_time(split_ms)
                        new_block['end_time'] = original_end_time
                        new_block['speaker'] = None
                        new_block['is_turn_start'] = False

                        if current_block['speaker'] is not None:
                            new_block['speaker'] = current_block['speaker']
                            new_block['is_turn_start'] = False
                    else:
                        current_block['text'] = text_before

                        new_block = current_block.copy()
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

        current_block = self.srt_blocks[self.current_block_index]
        next_block = self.srt_blocks[self.current_block_index + 1]

        if current_block['speaker'] is None or current_block['speaker'] == next_block['speaker']:
            current_block['text'] += " " + next_block['text']
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
        dialog = EditDialog(current_block['text'], self)

        if dialog.exec_() == QDialog.Accepted:
            new_text = dialog.get_text()
            current_block['text'] = new_text
            self.update_display()
            self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def open_pause_dialog(self):
        if not self.srt_blocks:
            return

        was_playing = False
        if self.auto_pause_enabled and self.is_playing:
            was_playing = True
            if self.audio_player:
                self.audio_player.pause()

        dialog = EnhancedPauseDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            option_index = dialog.selected_option
            self.handle_gat2_symbol(option_index)

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_gat2_symbol(self, option_index):
        symbols = ["(.)", "(-)", "(--)", "(---)", "(_._)", "(())", "<<>>", "[ ]", "°h", "°hh", "°hhh", "h°", "hh°", "hhh°"]

        if option_index == 4:
            self.handle_measured_pause()
        elif option_index == 5:
            self.handle_comment()
        elif option_index == 6:
            self.handle_action()
        elif option_index == 7:
            self.handle_overlap()
        else:
            symbol = symbols[option_index]
            self.handle_pause(symbol)

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
            dialog = PlacementDialog(current_block['text'], symbol, self)

            if dialog.exec_() == QDialog.Accepted:
                if dialog.create_new_line:
                    new_block = {
                        'index': max(block['index'] for block in self.srt_blocks) + 1,
                        'start_time': '',
                        'end_time': '',
                        'text': symbol,
                        'speaker': None,
                        'is_turn_start': False,
                        'is_pause': True
                    }
                    self.srt_blocks.insert(self.current_block_index + 1, new_block)
                else:
                    pos = dialog.placement_position
                    current_block['text'] = (current_block['text'][:pos] + " " + symbol +
                                           " " + current_block['text'][pos:]).strip()

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
        dialog = PlacementDialog(current_block['text'], symbol, self)

        if dialog.exec_() == QDialog.Accepted:
            if dialog.create_new_line:
                new_block = {
                    'index': max(block['index'] for block in self.srt_blocks) + 1,
                    'start_time': '',
                    'end_time': '',
                    'text': symbol,
                    'speaker': None,
                    'is_turn_start': False,
                    'is_pause': True
                }
                self.srt_blocks.insert(self.current_block_index + 1, new_block)
            else:
                pos = dialog.placement_position
                current_block['text'] = (current_block['text'][:pos] + " " + symbol +
                                       " " + current_block['text'][pos:]).strip()

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
                placement_dialog = PlacementDialog(current_block['text'], comment, self)

                if placement_dialog.exec_() == QDialog.Accepted:
                    if placement_dialog.create_new_line:
                        new_block = {
                            'index': max(block['index'] for block in self.srt_blocks) + 1,
                            'start_time': '',
                            'end_time': '',
                            'text': comment,
                            'speaker': None,
                            'is_turn_start': False,
                            'is_comment': True
                        }
                        self.srt_blocks.insert(self.current_block_index + 1, new_block)
                    else:
                        pos = placement_dialog.placement_position
                        current_block['text'] = (current_block['text'][:pos] + " " + comment +
                                               " " + current_block['text'][pos:]).strip()

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
        dialog = TextSelectionDialog(current_block['text'], self)

        if dialog.exec_() == QDialog.Accepted:
            start_pos, end_pos, selected_text = dialog.get_selection()
            if selected_text:
                action_text, ok = QInputDialog.getText(self, "Action Description",
                                                     f"Describe the action for '{selected_text}':")
                if ok and action_text:
                    before_text = current_block['text'][:start_pos]
                    after_text = current_block['text'][end_pos:]
                    current_block['text'] = f"{before_text}<<{action_text}> {selected_text}>{after_text}"
                    self.update_display()
                    self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def handle_overlap(self):
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

        dialog = TextSelectionDialog(current_block['text'], self)
        if dialog.exec_() == QDialog.Accepted:
            start_pos, end_pos, selected_text = dialog.get_selection()
            if selected_text:
                prev_dialog = TextSelectionDialog(prev_block['text'], self)
                prev_dialog.setWindowTitle("Select Overlapping Text in Previous Block")
                if prev_dialog.exec_() == QDialog.Accepted:
                    prev_start, prev_end, prev_selected = prev_dialog.get_selection()
                    if prev_selected:
                        chars_before_overlap = prev_start
                        indent_spaces = " " * chars_before_overlap

                        before_text = current_block['text'][:start_pos]
                        after_text = current_block['text'][end_pos:]
                        current_block['text'] = f"{before_text}{indent_spaces}[{selected_text}]{after_text}"

                        prev_before = prev_block['text'][:prev_start]
                        prev_after = prev_block['text'][prev_end:]
                        prev_block['text'] = f"{prev_before}[{prev_selected}]{prev_after}"

                        self.update_display()
                        self.mark_unsaved_changes()

        if was_playing and self.auto_pause_enabled:
            if self.audio_player:
                self.audio_player.play()

    def insert_empty_line(self):
        if not self.srt_blocks:
            return

        new_block = {
            'index': max(block['index'] for block in self.srt_blocks) + 1,
            'start_time': '',
            'end_time': '',
            'text': '',
            'speaker': None,
            'is_turn_start': False,
            'is_empty': True
        }
        self.srt_blocks.insert(self.current_block_index + 1, new_block)
        self.current_block_index += 1
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

    def export_transcript(self):
        if not self.srt_blocks:
            return

        project_info = {
            'name': self.project_name,
            'memo': self.project_memo
        }

        preview_dialog = ExportPreviewDialog(self, self.file_has_timestamps, project_info, self.audio_file_path)
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
                transcript_text = self.generate_srt_text(
                    include_diarization=settings['include_diarization'],
                    unassigned_handling=unassigned_handling
                )
            else:
                transcript_text = self.generate_transcript_text(
                    include_timestamps=settings['include_timestamps'],
                    convention=settings['convention'],
                    include_diarization=settings['include_diarization']
                )

            self.final_export(transcript_text, settings, project_info, unassigned_handling)

    def generate_transcript_text(self, include_timestamps=True, convention="gat2", include_diarization=True):
        """Generate transcript text with different conventions."""
        if convention == "dresing_pehl":
            return self.generate_dresing_pehl_text(include_timestamps, include_diarization)
        else:
            return self.generate_gat2_text(include_timestamps, include_diarization)

    def generate_gat2_text(self, include_timestamps=True, include_diarization=True):
        """Generate GAT2 format transcript."""
        total_lines = len([b for b in self.srt_blocks if b.get('speaker') is not None or b.get('is_pause') or b.get('is_comment') or b.get('is_empty')])
        line_digits = len(str(total_lines))

        max_speaker_length = 0
        for block in self.srt_blocks:
            if block['speaker'] is not None and block.get('is_turn_start', True):
                speaker_label = self.speakers[block['speaker']] + ":"
                max_speaker_length = max(max_speaker_length, len(speaker_label))

        max_speaker_length = max(max_speaker_length, 2)

        output_lines = []
        line_number = 1

        output_lines.append("")

        for block in self.srt_blocks:
            if block.get('is_pause') or block.get('is_comment') or block.get('is_empty'):
                if block['text']:
                    padded_line_num = str(line_number).zfill(line_digits)

                    if include_timestamps:
                        timestamp_spaces = " " * 13
                        speaker_spaces = " " * (max_speaker_length + 3)
                        line = f"{timestamp_spaces}{padded_line_num}   {speaker_spaces}{block['text']}"
                    else:
                        speaker_spaces = " " * (max_speaker_length + 3)
                        line = f"{padded_line_num}   {speaker_spaces}{block['text']}"

                    output_lines.append(line)
                    line_number += 1
            elif block['speaker'] is not None:
                padded_line_num = str(line_number).zfill(line_digits)

                if include_timestamps and block.get('start_time'):
                    time_parts = block['start_time'].split(':')
                    seconds_part = time_parts[2].split(',')[0] if ',' in time_parts[2] else time_parts[2]
                    gat_time = f"{{{time_parts[0]}:{time_parts[1]}:{seconds_part}}}"
                else:
                    gat_time = ""

                speaker_label = self.speakers[block['speaker']]

                if block.get('is_turn_start', True):
                    formatted_speaker = f"{speaker_label}:".ljust(max_speaker_length)
                    if include_timestamps and gat_time:
                        line = f"{gat_time}   {padded_line_num}   {formatted_speaker}   {block['text']}"
                    else:
                        line = f"{padded_line_num}   {formatted_speaker}   {block['text']}"
                else:
                    if include_timestamps:
                        timestamp_spaces = " " * 13
                        speaker_spaces = " " * (max_speaker_length + 3)
                        line = f"{timestamp_spaces}{padded_line_num}   {speaker_spaces}{block['text']}"
                    else:
                        speaker_spaces = " " * (max_speaker_length + 3)
                        line = f"{padded_line_num}   {speaker_spaces}{block['text']}"

                output_lines.append(line)
                line_number += 1

        if output_lines:
            output_lines[0] = output_lines[0].lstrip()

        return '\n'.join(output_lines)

    def generate_dresing_pehl_text(self, include_timestamps=True, include_diarization=True):
        """Generate Dresing & Pehl format transcript (sociological interviews)."""
        if not self.srt_blocks:
            return ""

        turns = []
        current_turn = None

        for block in self.srt_blocks:
            if block.get('is_pause') or block.get('is_comment') or block.get('is_empty'):
                continue

            if block['speaker'] is None:
                continue

            speaker_label = self.speakers[block['speaker']]

            if current_turn is None or current_turn['speaker'] != speaker_label or block.get('is_turn_start', True):
                if current_turn is not None:
                    turns.append(current_turn)

                current_turn = {
                    'speaker': speaker_label,
                    'blocks': [],
                    'start_time': block['start_time'] if include_timestamps else None,
                    'end_time': block['end_time'] if include_timestamps else None
                }

            current_turn['blocks'].append(block)
            if include_timestamps and block['end_time']:
                current_turn['end_time'] = block['end_time']

        if current_turn is not None:
            turns.append(current_turn)

        output_lines = []
        output_lines.append("")

        for turn in turns:
            turn_text = " ".join(block['text'].strip() for block in turn['blocks'])

            if include_diarization:
                line = f"{turn['speaker']}: {turn_text}"
            else:
                line = turn_text

            if include_timestamps and turn['start_time'] and turn['end_time']:
                start_seconds = self.time_to_seconds(turn['start_time'])
                end_seconds = self.time_to_seconds(turn['end_time'])

                start_hours = int(start_seconds // 3600)
                start_minutes = int((start_seconds % 3600) // 60)
                start_secs = int(start_seconds % 60)
                start_tenths = int((start_seconds - int(start_seconds)) * 10)

                end_hours = int(end_seconds // 3600)
                end_minutes = int((end_seconds % 3600) // 60)
                end_secs = int(end_seconds % 60)
                end_tenths = int((end_seconds - int(end_seconds)) * 10)

                timestamp = f"#{start_hours:02d}:{start_minutes:02d}:{start_secs:02d}-{start_tenths}#"

                line += f" {timestamp}"

            output_lines.append(line)
            output_lines.append("")

        return '\n'.join(output_lines)

    def time_to_seconds(self, time_str):
        """Convert time string to seconds with milliseconds as decimal."""
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

        return hours * 3600 + minutes * 60 + seconds + ms / 1000.0

    def generate_srt_text(self, include_diarization=True, unassigned_handling="skip"):
        """Generate SRT format text with optional diarization."""
        if not self.file_has_timestamps:
            return "SRT export requires timestamp information. Original file does not contain timestamps.\n\nNote: SRT files require precise timing information for each subtitle."

        blocks_with_timestamps = self.estimate_missing_timestamps()

        srt_blocks = []
        subtitle_index = 1

        for block in blocks_with_timestamps:
            if block.get('is_pause') or block.get('is_comment') or block.get('is_empty'):
                continue

            if block['speaker'] is None:
                if unassigned_handling == "skip":
                    continue
                elif unassigned_handling == "no_label":
                    speaker_prefix = ""
                elif unassigned_handling == "unknown":
                    speaker_prefix = "Unknown: "
            else:
                speaker_prefix = ""
                if include_diarization:
                    speaker_prefix = f"{self.speakers[block['speaker']]}: "

            start_time = self.format_srt_time(block['start_time'])
            end_time = self.format_srt_time(block['end_time'])

            srt_block = f"{subtitle_index}\n{start_time} --> {end_time}\n{speaker_prefix}{block['text']}\n"
            srt_blocks.append(srt_block)
            subtitle_index += 1

        return "\n".join(srt_blocks)

    def format_srt_time(self, time_str):
        """Convert time string to SRT format (HH:MM:SS,mmm)."""
        if not time_str:
            return "00:00:00,000"

        if ',' in time_str:
            return time_str
        elif ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 2:
                return f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)},000"
            elif len(parts) == 3:
                time_part = parts[2]
                if ',' in time_part:
                    time_part, ms_part = time_part.split(',')
                    return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{time_part.zfill(2)},{ms_part.zfill(3)}"
                else:
                    return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{time_part.zfill(2)},000"

        return "00:00:00,000"

    def estimate_missing_timestamps(self):
        """Estimate timestamps for blocks that don't have them."""
        if not self.srt_blocks:
            return []

        blocks = self.srt_blocks.copy()

        timestamped_blocks = []
        for i, block in enumerate(blocks):
            if block.get('start_time') and block.get('end_time'):
                timestamped_blocks.append((i, block))

        if not timestamped_blocks:
            return blocks

        segments = []
        last_timestamped_idx = -1

        for i, block in timestamped_blocks:
            if last_timestamped_idx == -1:
                segments.append({
                    'start_idx': 0,
                    'end_idx': i,
                    'start_time': None,
                    'end_time': block['start_time'],
                    'total_chars': sum(len(b['text']) for b in blocks[0:i])
                })
            else:
                segments.append({
                    'start_idx': last_timestamped_idx + 1,
                    'end_idx': i,
                    'start_time': blocks[last_timestamped_idx]['end_time'],
                    'end_time': block['start_time'],
                    'total_chars': sum(len(b['text']) for b in blocks[last_timestamped_idx + 1:i])
                })
            last_timestamped_idx = i

        if last_timestamped_idx < len(blocks) - 1:
            last_block = timestamped_blocks[-1][1] if timestamped_blocks else None
            segments.append({
                'start_idx': last_timestamped_idx + 1,
                'end_idx': len(blocks) - 1,
                'start_time': last_block['end_time'] if last_block else None,
                'end_time': None,
                'total_chars': sum(len(b['text']) for b in blocks[last_timestamped_idx + 1:])
            })

        for segment in segments:
            if segment['start_time'] and segment['end_time'] and segment['total_chars'] > 0:
                start_ms = self.time_to_ms(segment['start_time'])
                end_ms = self.time_to_ms(segment['end_time'])
                total_duration = end_ms - start_ms

                current_time = start_ms
                for i in range(segment['start_idx'], segment['end_idx'] + 1):
                    block = blocks[i]
                    if not block.get('start_time') or not block.get('end_time'):
                        block_chars = len(block['text'])
                        if segment['total_chars'] > 0:
                            block_duration = (block_chars / segment['total_chars']) * total_duration
                        else:
                            block_duration = 1000

                        block_duration = max(100, block_duration)

                        block['start_time'] = self.ms_to_time(current_time)
                        block['end_time'] = self.ms_to_time(current_time + block_duration)
                        current_time += block_duration

        return blocks

    def time_to_ms(self, time_str):
        """Convert time string to milliseconds."""
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

    def ms_to_time(self, ms):
        """Convert milliseconds to SRT time format."""
        hours = int(ms // 3600000)
        ms %= 3600000
        minutes = int(ms // 60000)
        ms %= 60000
        seconds = int(ms // 1000)
        milliseconds = int(ms % 1000)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

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

        if settings['convention'] != 'gat2':
            default_name += f"_{settings['convention']}"

        default_name += file_ext

        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export Transcript", default_name,
            f"{settings['format'].upper()} Files (*{file_ext})"
        )

        if not file_path:
            return

        try:
            if settings['format'] == 'srt':
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(transcript_text)

            elif settings['format'] == 'docx':
                try:
                    import docx
                    from docx.shared import Pt
                    from docx.enum.text import WD_ALIGN_PARAGRAPH

                    doc = docx.Document()

                    if settings.get('include_title', True) and project_info.get('name'):
                        title = doc.add_heading(project_info['name'], 0)
                        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

                    if settings.get('include_memo', True) and project_info.get('memo'):
                        doc.add_paragraph(f"Project Memo: {project_info['memo']}")

                    if settings.get('include_audio', True) and self.audio_file_path:
                        doc.add_paragraph(f"Audio File: {Path(self.audio_file_path).name}")

                    doc.add_paragraph()

                    for line in transcript_text.split('\n'):
                        if line.strip():
                            p = doc.add_paragraph(line)
                            font_name = 'Courier New'
                            if settings['convention'] == 'dresing_pehl':
                                font_name = 'Times New Roman'
                            for run in p.runs:
                                run.font.name = font_name
                                run.font.size = Pt(10)
                        else:
                            doc.add_paragraph()

                    doc.save(file_path)

                except ImportError:
                    QMessageBox.warning(self, "DOCX Export",
                        "python-docx library not found. Please install it with: pip install python-docx\n\n"
                        "Exporting as plain text instead.")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(transcript_text)

            elif settings['format'] == 'html':
                clean_text = transcript_text.lstrip()

                # Choose font based on convention
                font_family = "'Courier New', monospace"
                if settings['convention'] == "dresing_pehl":
                    font_family = "'Times New Roman', serif"

                    clean_text = transcript_text.lstrip()

                html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>GAT2 Transcript - {self.escape_html(project_info.get('name', 'Untitled'))}</title>
<style>
body {{
    font-family: {font_family};
    font-size: 10pt;
    line-height: 1.2;
    margin: 20px;
    white-space: pre;
}}
h1 {{
    font-family: Arial, sans-serif;
    color: #333;
    border-bottom: 2px solid #333;
    padding-bottom: 10px;
}}
</style>
</head>
<body>
{clean_text}
</body>
</html>"""
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            else:
                # Plain text export
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(transcript_text)

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


def main():
    app = QApplication(sys.argv)
    editor = SRTEditor()
    editor.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

