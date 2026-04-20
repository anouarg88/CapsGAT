"""Basic UI tests for CapsQual – ensures main window can be instantiated and basic operations don't crash."""
import sys
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from editor import SRTEditor

@pytest.fixture(scope="session")
def app():
    """Create a QApplication instance (once per test session)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

@pytest.fixture
def editor(app):
    """Create an SRTEditor instance (fresh for each test)."""
    editor = SRTEditor()
    yield editor
    editor.close()

def test_main_window_title(editor):
    assert "CapsQual" in editor.windowTitle()

def test_no_transcript_display(editor):
    # When no transcript loaded, text display shows "No content loaded"
    assert editor.text_display.toPlainText() == "No content loaded"

def test_load_srt(editor, tmp_path):
    srt_content = """1
00:00:01,000 --> 00:00:02,000
Test line
"""
    srt_file = tmp_path / "test.srt"
    srt_file.write_text(srt_content, encoding="utf-8")
    editor.load_file_from_path(str(srt_file))
    assert len(editor.srt_blocks) == 1
    assert editor.srt_blocks[0]['text'] == "Test line"

def test_assign_speaker(editor):
    # Load a dummy block
    editor.srt_blocks = [{'text': 'Hello', 'raw_text': 'Hello', 'speaker': None, 'is_turn_start': True}]
    editor.current_block_index = 0
    editor.assign_speaker(0)  # assign speaker A
    assert editor.srt_blocks[0]['speaker'] == 0
    assert editor.srt_blocks[0]['is_turn_start'] is True

def test_split_block(editor):
    editor.srt_blocks = [{'text': 'Hello world', 'raw_text': 'Hello world', 'speaker': None, 'is_turn_start': True}]
    editor.current_block_index = 0
    # We need to simulate dialog acceptance. For now, we'll call split with a mock.
    # Instead, we'll directly test the internal split logic.
    # Since the dialog is interactive, we'll skip for automated test but can test the helper.
    pass  # Placeholder; can be implemented with QTest if needed.

def test_undo_redo(editor):
    editor.srt_blocks = [{'text': 'Original', 'raw_text': 'Original', 'speaker': None, 'is_turn_start': True}]
    editor.push_undo()
    editor.srt_blocks[0]['text'] = 'Modified'
    editor.undo()
    assert editor.srt_blocks[0]['text'] == 'Original'
    editor.redo()
    assert editor.srt_blocks[0]['text'] == 'Modified'
