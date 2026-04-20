"""Unit tests for export functions (GAT2, Dresing & Pehl, TiQ, SRT)."""
import pytest
import re
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication
from editor import SRTEditor

# ----------------------------------------------------------------------
# Fixtures
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
        yield editor
        editor.close()

# ----------------------------------------------------------------------
# GAT2 export tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
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

@pytest.mark.timeout(60)
def test_gat2_concatenate_turns(editor):
    # Disable timestamps to avoid interference
    text = editor.generate_gat2_text(
        include_timestamps=False,
        concatenate_turns=True,
        delimiter_choice="space",
        wrap_enabled=False
    )
    # Remove line numbers (first column) for simpler check
    lines = text.split('\n')
    # The first line should contain the concatenated text
    # Example: "001   A:   Hello world Second line"
    # We can check for "Hello world Second line" in any line
    assert any("Hello world Second line" in line for line in lines)
    assert "Reply" in text

@pytest.mark.timeout(60)
def test_gat2_no_diarization(editor):
    # Disable timestamps
    text = editor.generate_gat2_text(
        include_timestamps=False,
        include_diarization=False
    )
    assert "A:" not in text
    assert "Hello world" in text

# ----------------------------------------------------------------------
# Dresing & Pehl export tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_dresing_pehl_basic(editor):
    # Disable timestamps for simpler content check
    text = editor.generate_dresing_pehl_text(
        include_timestamps=False,
        include_diarization=True,
        add_blank_line=False
    )
    assert "A:" in text
    assert "Hello world" in text
    assert "Second line" in text
    assert "B:" in text
    assert "Reply" in text
    assert "(.) Pause block" in text

@pytest.mark.timeout(60)
def test_dresing_pehl_no_timestamp(editor):
    text = editor.generate_dresing_pehl_text(include_timestamps=False)
    assert "#" not in text
    assert "{" not in text

# ----------------------------------------------------------------------
# TiQ export tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_tiq_basic(editor):
    # Keep timestamps to test format, but content check can be relaxed
    text = editor.generate_tiq_text(
        include_timestamps=True,
        include_diarization=True,
        wrap_enabled=False,
        add_blank_line=False
    )
    assert "A:" in text
    assert "Hello world" in text
    assert "Second line" in text
    assert "B:" in text
    assert "Reply" in text
    # Check for timestamp format
    assert re.search(r'#\d{2}:\d{2}:\d{2}-\d#', text) or re.search(r'{\d{2}:\d{2}:\d{2}}', text)

@pytest.mark.timeout(60)
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
@pytest.mark.timeout(60)
def test_srt_export_basic(editor):
    srt = editor.generate_srt_text(include_diarization=True, unassigned_handling="skip")
    assert "Speaker A: Hello world" in srt
    assert "Speaker B: Reply" in srt
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "(.) Pause block" not in srt

@pytest.mark.timeout(60)
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
@pytest.mark.timeout(60)
def test_time_conversion(editor):
    assert editor.time_to_seconds("00:01:30,500") == 90.5
    assert editor.time_to_ms("00:01:30,500") == 90500
