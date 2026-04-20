"""Unit tests for export functions (GAT2, Dresing & Pehl, TiQ, SRT)."""
import pytest
from editor import SRTEditor

# ----------------------------------------------------------------------
# Helper to create a minimal editor with sample blocks
# ----------------------------------------------------------------------
def create_editor_with_blocks():
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
    return editor

# ----------------------------------------------------------------------
# GAT2 export tests
# ----------------------------------------------------------------------
def test_gat2_basic_export():
    editor = create_editor_with_blocks()
    text = editor.generate_gat2_text(
        include_timestamps=True,
        timestamp_style="curly",
        include_diarization=True,
        wrap_enabled=False,
        add_blank_line=False,
        concatenate_turns=False
    )
    # Should contain line numbers, timestamps, speaker labels
    assert "{00:00:00}" in text
    assert "A: Hello world" in text
    assert "B: Reply" in text
    # Pause block should be included (since is_pause)
    assert "(.) Pause block" in text

def test_gat2_concatenate_turns():
    editor = create_editor_with_blocks()
    text = editor.generate_gat2_text(
        include_timestamps=True,
        concatenate_turns=True,
        delimiter_choice="space",
        wrap_enabled=False
    )
    # First two blocks (same speaker) should be joined with space
    assert "Hello world Second line" in text
    assert "Reply" in text

def test_gat2_no_diarization():
    editor = create_editor_with_blocks()
    text = editor.generate_gat2_text(include_diarization=False)
    assert "A:" not in text
    assert "Hello world" in text

# ----------------------------------------------------------------------
# Dresing & Pehl export tests
# ----------------------------------------------------------------------
def test_dresing_pehl_basic():
    editor = create_editor_with_blocks()
    text = editor.generate_dresing_pehl_text(
        include_timestamps=True,
        include_diarization=True,
        add_blank_line=False
    )
    # Should have speaker labels and concatenated turn texts
    assert "A: Hello world Second line" in text
    assert "B: Reply" in text
    assert "(.) Pause block" in text   # pauses included
    # Timestamp should be appended
    assert "#00:00:00-0#" in text or "{00:00:00}" in text  # depends on style

def test_dresing_pehl_no_timestamp():
    editor = create_editor_with_blocks()
    text = editor.generate_dresing_pehl_text(include_timestamps=False)
    assert "#" not in text
    assert "{" not in text

# ----------------------------------------------------------------------
# TiQ export tests
# ----------------------------------------------------------------------
def test_tiq_basic():
    editor = create_editor_with_blocks()
    text = editor.generate_tiq_text(
        include_timestamps=True,
        include_diarization=True,
        wrap_enabled=False,
        add_blank_line=False
    )
    lines = text.split('\n')
    # First line should have line number, speaker, turn text
    assert "A: Hello world Second line" in lines[0] or "A: Hello world Second line" in text
    assert "B: Reply" in text
    # Timestamp should be appended to last line of each turn
    assert "#00:00:00-0#" in lines[0] or "#00:00:00-0#" in text

def test_tiq_wrapping():
    editor = create_editor_with_blocks()
    # Force a very narrow wrap to test
    text = editor.generate_tiq_text(
        wrap_enabled=True,
        wrap_length=20,
        character_wrap=False,
        include_diarization=True
    )
    # No specific assertion, just ensure no crash
    assert len(text) > 0

# ----------------------------------------------------------------------
# SRT export tests
# ----------------------------------------------------------------------
def test_srt_export_basic():
    editor = create_editor_with_blocks()
    srt = editor.generate_srt_text(include_diarization=True, unassigned_handling="skip")
    assert "Speaker A: Hello world" in srt
    assert "Speaker B: Reply" in srt
    assert "00:00:00,000 --> 00:00:02,000" in srt
    # Pause block (is_pause) should be skipped
    assert "(.) Pause block" not in srt

def test_srt_unassigned_handling():
    editor = create_editor_with_blocks()
    # Add an unassigned non‑pause block
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
# Timestamp formatting
# ----------------------------------------------------------------------
def test_time_conversion():
    editor = SRTEditor()
    assert editor.time_to_seconds("00:01:30,500") == 90.5
    assert editor.time_to_seconds("01:02:03,004") == 3723.004
    assert editor.time_to_ms("00:01:30,500") == 90500
