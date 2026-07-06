"""Basic UI and non‑UI tests for CapsQual – focuses on initialisation and core logic without GUI."""
import sys
import pytest
from unittest.mock import patch, Mock
from PyQt5.QtWidgets import QApplication
from editor import SRTEditor
from export import (
    format_timestamp, time_to_seconds, time_to_ms, ms_to_time
)

@pytest.fixture(scope="module")
def app():
    """Create a QApplication instance (required for any Qt object)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

@pytest.fixture
def editor(app):
    """Create an SRTEditor instance with the UI initialisation mocked."""
    with patch.object(SRTEditor, 'init_ui'):
        editor = SRTEditor()
        # Provide minimal UI-like attributes for methods that assume widgets exist.
        editor.speaker_count_label = Mock()
        editor.btn_add_speaker = Mock()
        editor.btn_remove_speaker = Mock()
        editor.create_speaker_widgets = Mock()
        editor.setup_shortcuts = Mock()
        editor.update_display = Mock()
        editor.update_speaker_buttons = Mock()
        yield editor
        editor.has_unsaved_changes = False
        editor.close()

def test_initial_attributes(editor):
    """Check that basic attributes are set correctly before init_ui."""
    assert editor.srt_blocks == []
    assert editor.speakers == ["A", "B", "C", "D"]
    assert editor.current_block_index == 0
    assert editor.file_has_timestamps is True
    assert editor.project_name == ""
    assert editor.project_memo == ""
    assert editor.cjk_mode is False

def test_speaker_management(editor):
    """Test speaker count adjustment and renaming (no UI needed)."""
    # Initial speaker count
    assert len(editor.speakers) == 4
    # Increase
    editor.increase_speaker_count()
    assert len(editor.speakers) == 5
    assert editor.speakers[4] == "E"   # next letter
    # Decrease (but need to handle assigned blocks – none assigned)
    editor.decrease_speaker_count()
    assert len(editor.speakers) == 4

def test_undo_redo_basic(editor):
    """Test undo/redo stack operations."""
    editor.srt_blocks = [{'text': 'Original', 'speaker': None}]
    editor.push_undo()
    editor.srt_blocks[0]['text'] = 'Modified'
    editor.undo()
    assert editor.srt_blocks[0]['text'] == 'Original'
    editor.redo()
    assert editor.srt_blocks[0]['text'] == 'Modified'

def test_mark_unsaved_changes(editor):
    """Test the unsaved changes flag and window title."""
    editor.project_name = "Test"
    editor.mark_unsaved_changes()
    assert editor.has_unsaved_changes is True
    assert "*" in editor.windowTitle()
    editor.clear_unsaved_changes()
    assert editor.has_unsaved_changes is False
    assert "*" not in editor.windowTitle()

def test_format_timestamp(editor):
    """Test timestamp formatting."""
    assert format_timestamp(90.5, "curly") == "{00:01:30}"
    assert format_timestamp(90.5, "hash") == "#00:01:30-5#"
    assert format_timestamp(90.5, "bracket") == "[00:01:30]"

def test_time_conversion(editor):
    """Test helper methods for time conversion."""
    assert time_to_seconds("00:01:30,500") == 90.5
    assert time_to_ms("00:01:30,500") == 90500
    assert ms_to_time(90500) == "00:01:30,500"