"""Unit tests for parsing various subtitle formats."""
import pytest
import json
import tempfile
from pathlib import Path
from editor import SRTEditor

# ----------------------------------------------------------------------
# SRT parsing
# ----------------------------------------------------------------------

def test_parse_srt_basic():
    editor = SRTEditor()
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

def test_parse_srt_malformed():
    editor = SRTEditor()
    content = "1\n00:00:01,000 --> 00:00:04,000"
    blocks = editor.parse_srt(content)
    assert blocks == []   # invalid block should be ignored

def test_parse_srt_extra_newlines():
    editor = SRTEditor()
    content = "\n\n1\n00:00:01,000 --> 00:00:04,000\nText\n\n"
    blocks = editor.parse_srt(content)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Text"

# ----------------------------------------------------------------------
# Plain text parsing
# ----------------------------------------------------------------------

def test_parse_text_basic():
    editor = SRTEditor()
    content = "Line one\nLine two\n\nLine three"
    blocks = editor.parse_text(content)
    assert len(blocks) == 3
    assert blocks[0]['text'] == "Line one"
    assert blocks[1]['text'] == "Line two"
    assert blocks[2]['text'] == "Line three"
    for block in blocks:
        assert block['start_time'] == ''
        assert block['end_time'] == ''

# ----------------------------------------------------------------------
# TSV parsing
# ----------------------------------------------------------------------

def test_parse_tsv_basic():
    editor = SRTEditor()
    content = "start\tend\ttext\n1000\t2000\tHello\n2000\t3000\tWorld"
    blocks = editor.parse_tsv(content)
    assert len(blocks) == 2
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:02,000"
    assert blocks[0]['text'] == "Hello"
    assert blocks[1]['text'] == "World"

def test_parse_tsv_no_header():
    editor = SRTEditor()
    content = "1000\t2000\tHello\n2000\t3000\tWorld"
    blocks = editor.parse_tsv(content)
    assert len(blocks) == 2  # first line not skipped because no header detection
    # Actually parse_tsv skips first line only if it contains "start". So without header, it's fine.
    assert blocks[0]['text'] == "Hello"

# ----------------------------------------------------------------------
# JSON parsing
# ----------------------------------------------------------------------

def test_parse_json_tokens_format():
    editor = SRTEditor()
    data = {
        "tokens": ["Hello", " ", "world"],
        "timestamps": [0.5, 0.6, 0.7]
    }
    # We need to mock dialog or simulate user choice? For testing, we'll override
    # We'll patch JsonImportDialog to return "one_block"
    with patch('dialogs.JsonImportDialog') as mock_dialog:
        mock_dialog.return_value.exec_.return_value = QDialog.Accepted
        mock_dialog.return_value.get_import_option.return_value = "one_block"
        blocks = editor.parse_json(data)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Helloworld"   # concatenated

def test_parse_json_segments_format():
    editor = SRTEditor()
    data = {"segments": [{"start": 1.5, "end": 3.2, "text": "Hello"}]}
    blocks = editor.parse_json(data)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello"
    assert blocks[0]['start_time'] == "00:00:01,500"

def test_parse_json_text_only():
    editor = SRTEditor()
    data = {"text": "Just a sentence"}
    blocks = editor.parse_json(data)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Just a sentence"

def test_parse_json_list():
    editor = SRTEditor()
    data = [{"text": "First"}, {"text": "Second"}]
    blocks = editor.parse_json(data)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "First"
    assert blocks[1]['text'] == "Second"

def test_parse_json_transcript_blocks():
    editor = SRTEditor()
    data = {"transcript": [{"text": "A"}, {"text": "B"}]}
    blocks = editor.parse_json(data)
    assert len(blocks) == 2

# ----------------------------------------------------------------------
# Helpers for mocking
# ----------------------------------------------------------------------
from unittest.mock import patch
from PyQt5.QtWidgets import QDialog
