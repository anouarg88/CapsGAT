"""Unit tests for parsing various subtitle formats."""
import pytest
import json
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication
from editor import SRTEditor

# ----------------------------------------------------------------------
# Fixture to create a minimal editor (UI mocked)
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()
    app.processEvents()

@pytest.fixture
def editor(app):
    with patch.object(SRTEditor, 'init_ui'):
        editor = SRTEditor()
        # Ensure required attributes exist
        editor.srt_blocks = []
        editor.speakers = ["A", "B", "C", "D"]
        editor.cjk_mode = False
        yield editor
        editor.close()

# ----------------------------------------------------------------------
# SRT parsing
# ----------------------------------------------------------------------
def test_parse_srt_basic(editor):
    content = """1
00:00:01,000 --> 00:00:04,000
Hello world

2
00:00:05,000 --> 00:00:07,500
Second line"""
    blocks = editor.parse_srt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Hello world"
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:04,000"
    assert blocks[1]['text'] == "Second line"

def test_parse_srt_malformed(editor):
    content = "1\n00:00:01,000 --> 00:00:04,000"
    blocks = editor.parse_srt(content)
    assert blocks == []

def test_parse_text_basic(editor):
    content = "Line one\nLine two\n\nLine three"
    blocks = editor.parse_text(content)
    assert len(blocks) == 3
    assert blocks[0]['text'] == "Line one"
    assert blocks[1]['text'] == "Line two"
    assert blocks[2]['text'] == "Line three"

def test_parse_tsv_basic(editor):
    content = "start\tend\ttext\n1000\t2000\tHello\n2000\t3000\tWorld"
    blocks = editor.parse_tsv(content)
    assert len(blocks) == 2
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:02,000"
    assert blocks[0]['text'] == "Hello"

def test_parse_json_tokens_format(editor):
    data = {"tokens": ["Hello", " ", "world"], "timestamps": [0.5, 0.6, 0.7]}
    with patch('dialogs.JsonImportDialog') as mock_dialog:
        mock_dialog.return_value.exec_.return_value = 1  # QDialog.Accepted
        mock_dialog.return_value.get_import_option.return_value = "one_block"
        blocks = editor.parse_json(data)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Helloworld"

def test_parse_json_segments_format(editor):
    data = {"segments": [{"start": 1.5, "end": 3.2, "text": "Hello"}]}
    blocks = editor.parse_json(data)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello"
    assert blocks[0]['start_time'] == "00:00:01,500"
