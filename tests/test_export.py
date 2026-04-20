"""Unit tests for export functions (GAT2, Dresing & Pehl, TiQ, SRT)."""
import pytest
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication
from editor import SRTEditor

# ----------------------------------------------------------------------
# Fixture to create a minimal editor with test blocks (UI mocked)
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def editor(app):
    with patch.object(SRTEditor, 'init_ui'):
        editor = SRTEditor()
        editor.srt_blocks = [
            {
                'index': 1,
                'start_time': '00:00:00,000',
                'end_time': '00:00:02,000',
                'text': 'Speaker A: Hello world',
                'raw_text': 'Speaker A: Hello world',
                'speaker': 0,
                'is_turn_start': True
            },
            {
                'index': 2,
                'start_time': '00:00:02,500',
                'end_time': '00:00:04,000',
                'text': 'Speaker A: Second line',
                'raw_text': 'Speaker A: Second line',
                'speaker': 0,
                'is_turn_start': False
            },
            {
                'index': 3,
                'start_time': '00:00:04,500',
                'end_time': '00:00:06,000',
                'text': 'Speaker B: Reply',
                'raw_text': 'Speaker B: Reply',
                'speaker': 1,
                'is_turn_start': True
            },
            {
                'index': 4,
                'start_time': '00:00:06,500',
                'end_time': '00:00:08,000',
                'text': '(.) Pause block',
                'raw_text': '(.) Pause block',
                'speaker': None,
                'is_turn_start': False,
                'is_pause': True
            }
        ]
        editor.speakers = ["A", "B"]
        editor.cjk_mode = False
        # Ensure helper methods exist (they are inherited)
        yield editor
        editor.close()

# ----------------------------------------------------------------------
# GAT2 export tests
# ----------------------------------------------------------------------
def test_gat2_basic_export(editor):
    text = editor.generate_gat2_text(
        include_timestamps=True,
        timestamp_style="curly",
        include_diarization=True,
        wrap_enabled=False,
        add_blank_line=False,
        concatenate_turns=False
    )
    assert "{00:00:00}" in text
    assert "A: Hello world" in text
    assert "B: Reply" in text
    assert "(.) Pause block" in text

def test_gat2_concatenate_turns(editor):
    text = editor.generate_gat2_text(
        include_timestamps=True,
        concatenate_turns=True,
        delimiter_choice="space",
        wrap_enabled=False
    )
    # Check that the two lines appear in order
    assert "Hello world" in text
    assert "Second line" in text
    import re
    # Remove line numbers and timestamps for a cleaner check
    cleaned = re.sub(r'\d+\s+\S+\s+', '', text)  # remove line numbers and timestamps
    assert "Hello world Second line" in cleaned or "Hello world Second line" in text

def test_gat2_no_diarization(editor):
    text = editor.generate_gat2_text(include_diarization=False)
    assert "A:" not in text
    assert "Hello world" in text

def test_dresing_pehl_basic(editor):
    text = editor.generate_dresing_pehl_text(
        include_timestamps=True,
        include_diarization=True,
        add_blank_line=False
    )
    # Check for speaker labels and combined text (order may vary)
    assert "A:" in text
    assert "Hello world" in text
    assert "Second line" in text
    assert "B:" in text
    assert "Reply" in text
    assert "(.) Pause block" in text

def test_dresing_pehl_no_timestamp(editor):
    text = editor.generate_dresing_pehl_text(include_timestamps=False)
    assert "#" not in text
    assert "{" not in text

def test_tiq_basic(editor):
    text = editor.generate_tiq_text(
        include_timestamps=True,
        include_diarization=True,
        wrap_enabled=False,
        add_blank_line=False
    )
    # TiQ output includes line numbers and timestamps at the end of the turn
    assert "A:" in text
    assert "Hello world" in text
    assert "Second line" in text
    assert "B:" in text
    assert "Reply" in text
    # Timestamp may be in various formats, so just check that something like #00:00:00 exists
    assert re.search(r'#\d{2}:\d{2}:\d{2}-\d#', text) or re.search(r'{\d{2}:\d{2}:\d{2}}', text)

def test_tiq_wrapping(editor):
    text = editor.generate_tiq_text(
        wrap_enabled=True,
        wrap_length=20,
        character_wrap=False,
        include_diarization=True
    )
    assert len(text) > 0

# ----------------------------------------------------------------------
# SRT export tests
# ----------------------------------------------------------------------
def test_srt_export_basic(editor):
    srt = editor.generate_srt_text(include_diarization=True, unassigned_handling="skip")
    assert "Speaker A: Hello world" in srt
    assert "Speaker B: Reply" in srt
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "(.) Pause block" not in srt

def test_srt_unassigned_handling(editor):
    editor.srt_blocks.append({
        'text': 'Unassigned text',
        'raw_text': 'Unassigned text',
        'speaker': None,
        'is_turn_start': True,
        'start_time': '00:00:08,000',
        'end_time': '00:00:09,000'
    })
    srt = editor.generate_srt_text(unassigned_handling="skip")
    assert "Unassigned text" not in srt
    srt = editor.generate_srt_text(unassigned_handling="no_label")
    assert "Unassigned text" in srt
    srt = editor.generate_srt_text(unassigned_handling="unknown")
    assert "Unknown: Unassigned text" in srt

# ----------------------------------------------------------------------
# Timestamp conversion tests
# ----------------------------------------------------------------------
def test_time_conversion(editor):
    assert editor.time_to_seconds("00:01:30,500") == 90.5
    assert editor.time_to_ms("00:01:30,500") == 90500
