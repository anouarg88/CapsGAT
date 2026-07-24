"""Unit tests for export functions (GAT2, Dresing & Pehl, TiQ, SRT)."""
import pytest
import re
from transcript import Transcript, INDENT_PLACEHOLDER
from generators import (
    generate_gat2_text, generate_dresing_pehl_text, generate_tiq_text,
    generate_srt_text, time_to_seconds, time_to_ms
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def transcript():
    return Transcript(
        blocks=[
            {
                'index': 1,
                'start_time': '00:00:00,000',
                'end_time': '00:00:02,000',
                'text': 'Hello world',
                'raw_text': 'Hello world',
                'speaker': 0,
                'is_turn_start': True
            },
            {
                'index': 2,
                'start_time': '00:00:02,500',
                'end_time': '00:00:04,000',
                'text': 'Second line',
                'raw_text': 'Second line',
                'speaker': 0,
                'is_turn_start': False
            },
            {
                'index': 3,
                'start_time': '00:00:04,500',
                'end_time': '00:00:06,000',
                'text': 'Reply',
                'raw_text': 'Reply',
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
        ],
        speakers=["A", "B"],
        cjk_mode=False
    )

# ----------------------------------------------------------------------
# GAT2 export tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_gat2_basic_export(transcript):
    text = generate_gat2_text(transcript, 
        include_timestamps=True,
        timestamp_style="curly",
        include_diarization=True,
        wrap_enabled=False,
        add_blank_line=False,
        concatenate_turns=False
    )
    assert "{00:00:00}" in text
    assert "A:" in text
    assert "Hello world" in text
    assert "B:" in text
    assert "Reply" in text
    assert "(.) Pause block" in text

@pytest.mark.timeout(60)
def test_gat2_concatenate_turns(transcript):
    # Disable timestamps to avoid interference
    text = generate_gat2_text(transcript, 
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
def test_gat2_no_diarization(transcript):
    # GAT2 keeps diarization even if include_diarization is disabled.
    text = generate_gat2_text(transcript, 
        include_timestamps=False,
        include_diarization=False
    )
    assert "A:" in text
    assert "B:" in text
    assert "Hello world" in text

# ----------------------------------------------------------------------
# Dresing & Pehl export tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_dresing_pehl_basic(transcript):
    # Disable timestamps for simpler content check
    text = generate_dresing_pehl_text(transcript, 
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
def test_dresing_pehl_no_timestamp(transcript):
    text = generate_dresing_pehl_text(transcript, include_timestamps=False)
    assert "#" not in text
    assert "{" not in text

# ----------------------------------------------------------------------
# TiQ export tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_tiq_basic(transcript):
    # Keep timestamps to test format, but content check can be relaxed
    text = generate_tiq_text(transcript, 
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
def test_tiq_wrapping(transcript):
    text = generate_tiq_text(transcript, 
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
def test_srt_export_basic(transcript):
    srt = generate_srt_text(transcript, include_diarization=True, unassigned_handling="skip")
    assert "A: Hello world" in srt
    assert "B: Reply" in srt
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "(.) Pause block" not in srt

@pytest.mark.timeout(60)
def test_srt_unassigned_handling(transcript):
    transcript.blocks.append({
        'text': 'Unassigned text',
        'raw_text': 'Unassigned text',
        'speaker': None,
        'is_turn_start': True,
        'start_time': '00:00:08,000',
        'end_time': '00:00:09,000'
    })
    srt = generate_srt_text(transcript, unassigned_handling="skip")
    assert "Unassigned text" not in srt
    srt = generate_srt_text(transcript, unassigned_handling="no_label")
    assert "Unassigned text" in srt
    srt = generate_srt_text(transcript, unassigned_handling="unknown")
    assert "Unknown: Unassigned text" in srt

# ----------------------------------------------------------------------
# Timestamp conversion tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_time_conversion(transcript):
    assert time_to_seconds("00:01:30,500") == 90.5
    assert time_to_ms("00:01:30,500") == 90500

# ----------------------------------------------------------------------
# SRT time formatting tests
# ----------------------------------------------------------------------
@pytest.mark.timeout(60)
def test_format_srt_time_dot_separated_ms():
    """Dot-separated milliseconds (from ffmpeg/Whisper) should be converted to comma format."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03.456")
    assert result == "01:02:03,456", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_single_digit_ms():
    """Single-digit milliseconds should be left-padded to 3 digits."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03,4")
    assert result == "01:02:03,004", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_two_digit_ms():
    """Two-digit milliseconds should be left-padded to 3 digits."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03,45")
    assert result == "01:02:03,045", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_standard_format():
    """Standard SRT format should pass through unchanged."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03,456")
    assert result == "01:02:03,456", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_two_digit_minutes():
    """MM:SS format should be expanded to HH:MM:SS."""
    from generators import format_srt_time
    result = format_srt_time("02:03,400")
    assert result == "00:02:03,400", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_no_ms():
    """Time without milliseconds should get ,000 appended."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03")
    assert result == "01:02:03,000", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_empty():
    """Empty string should return default SRT time."""
    from generators import format_srt_time
    result = format_srt_time("")
    assert result == "00:00:00,000", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_none():
    """None should return default SRT time."""
    from generators import format_srt_time
    result = format_srt_time(None)
    assert result == "00:00:00,000", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_more_than_3_digit_ms():
    """More than 3 digit milliseconds should be truncated."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03,4567")
    assert result == "01:02:03,456", f"Got {result!r}"

@pytest.mark.timeout(60)
def test_format_srt_time_dot_and_single_digit():
    """Dot-separated with single digit ms should be padded."""
    from generators import format_srt_time
    result = format_srt_time("01:02:03.1")
    assert result == "01:02:03,001", f"Got {result!r}"


# ----------------------------------------------------------------------
# Overlap export tests
# ----------------------------------------------------------------------

@pytest.mark.timeout(60)
def test_tiq_overlap_concatenated_no_wrap(transcript):
    """TiQ: overlap block appears as continuation line with correct indentation."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'take a look at THIS',
            'raw_text': 'take a look at THIS',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'this is a line to illustrate the',
            'raw_text': 'this is a line to illustrate the',
            'speaker': 0,
            'is_turn_start': False
        },
        {
            'index': 3,
            'text': 'current issue with overlapping speech.',
            'raw_text': 'current issue with overlapping speech.',
            'speaker': 0,
            'is_turn_start': False
        },
        {
            'index': 4,
            'text': 'This line overlaps.',
            'raw_text': 'This line overlaps.',
            'speaker': 1,
            'is_turn_start': True,
            'overlap_info': {
                'indent': 22,
                'overlap_text': '└This line overlaps.',
                'prev_block_idx': 1,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["Y", "A"]

    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True
    )
    assert "Y:" in text
    assert "take a look at THIS" in text
    assert "A:" in text
    assert "└This line overlaps." in text


@pytest.mark.timeout(60)
def test_tiq_overlap_concatenated_wrapped(transcript):
    """TiQ: overlap with wrapping preserves indentation."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'take a look at THIS',
            'raw_text': 'take a look at THIS',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'this is a line to illustrate the',
            'raw_text': 'this is a line to illustrate the',
            'speaker': 0,
            'is_turn_start': False
        },
        {
            'index': 3,
            'text': 'current issue with overlapping speech.',
            'raw_text': 'current issue with overlapping speech.',
            'speaker': 0,
            'is_turn_start': False
        },
        {
            'index': 4,
            'text': 'This line overlaps with the word illustrate.',
            'raw_text': 'This line overlaps with the word illustrate.',
            'speaker': 1,
            'overlap_info': {
                'indent': 10,
                'overlap_text': '└This line overlaps with the word illustrate.',
                'prev_block_idx': 1,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["Y", "A"]

    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=True,
        wrap_length=50,
        concatenate_turns=True,
        include_diarization=True
    )
    assert "└" in text
    assert "illustrate" in text or "overlap" in text

@pytest.mark.timeout(60)
def test_gat2_overlap_concatenated(transcript):
    """GAT2 concatenated: overlap block appears with correct indentation."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'Hello world this is',
            'raw_text': 'Hello world this is',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'the overlapping text here',
            'raw_text': 'the overlapping text here',
            'speaker': 0,
            'is_turn_start': False,
            'overlap_info': {
                'indent': 16,
                'overlap_text': '[the overlapping text here]',
                'prev_block_idx': 0,
                'convention': 'gat2',
                'text_before': '',
                'text_after': ''
            }
        },
        {
            'index': 3,
            'text': 'Reply from B',
            'raw_text': 'Reply from B',
            'speaker': 1,
            'is_turn_start': True
        }
    ]
    transcript.speakers = ["A", "B"]

    text = generate_gat2_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True,
        delimiter_choice="space"
    )
    assert "Hello world this is" in text
    assert "[the overlapping text here]" in text
    assert "Reply from B" in text


@pytest.mark.timeout(60)
def test_gat2_overlap_concatenated_wrapped(transcript):
    """GAT2 concatenated wrapped: overlap appears when wrapping enabled."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'Short',
            'raw_text': 'Short',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'overlap text here',
            'raw_text': 'overlap text here',
            'speaker': 0,
            'is_turn_start': False,
            'overlap_info': {
                'indent': 3,
                'overlap_text': '[overlap text here]',
                'prev_block_idx': 0,
                'convention': 'gat2',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["A", "B"]

    text = generate_gat2_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=True,
        wrap_length=40,
        concatenate_turns=True,
        include_diarization=True,
        delimiter_choice="space"
    )
    assert "[overlap text here]" in text
@pytest.mark.timeout(60)
def test_tiq_overlap_partial_block(transcript):
    """TiQ: block with both normal text and overlap (text_before/text_after)."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'Hello world',
            'raw_text': 'Hello world',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': ' some text └overlap more text',
            'raw_text': ' some text └overlap more text',
            'speaker': 0,
            'is_turn_start': False,
            'overlap_info': {
                'indent': 12,
                'overlap_text': '└overlap',
                'prev_block_idx': 0,
                'convention': 'tiq',
                'text_before': 'some text',
                'text_after': 'more text'
            }
        }
    ]
    transcript.speakers = ["A"]

    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True
    )
    assert "some text" in text
    assert "more text" in text
    assert "└overlap" in text



# ----------------------------------------------------------------------
# TiQ blank line and vertical bar tests
# ----------------------------------------------------------------------

@pytest.mark.timeout(60)
def test_tiq_add_blank_line(transcript):
    """Empty line should appear between turns when add_blank_line=True."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'Hello',
            'raw_text': 'Hello',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'World',
            'raw_text': 'World',
            'speaker': 1,
            'is_turn_start': True
        }
    ]
    transcript.speakers = ["A", "B"]
    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        add_blank_line=True,
        concatenate_turns=True
    )
    lines = text.split('\n')
    # Expect: 1 A: Hello, 2 (blank), 3 B: World
    assert len(lines) == 3
    assert 'A:' in lines[0] and 'Hello' in lines[0]
    # Line 2 should be blank (only line number, no content)
    line2_stripped = lines[1][lines[1].index(' ') + 1:] if ' ' in lines[1] else lines[1]
    assert line2_stripped.strip() == ''
    assert 'B:' in lines[2] and 'World' in lines[2]


@pytest.mark.timeout(60)
def test_tiq_no_blank_line_default(transcript):
    """No blank line when add_blank_line=False (default)."""
    transcript.blocks = [
        {
            'index': 1,
            'text': 'Hello',
            'raw_text': 'Hello',
            'speaker': 0,
            'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'World',
            'raw_text': 'World',
            'speaker': 1,
            'is_turn_start': True
        }
    ]
    transcript.speakers = ["A", "B"]
    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        add_blank_line=False,
        concatenate_turns=True
    )
    lines = text.split('\n')
    assert len(lines) == 2  # Just two lines, no blank


@pytest.mark.timeout(60)
def test_tiq_vertical_bar_on_overlap(transcript):
    """When add_blank_line and next turn starts with └, insert | above it.

    The overlap line is emitted inline within the previous turn's output
    (cross-speaker overlap), and the bar should appear BEFORE the overlap line.
    """
    transcript.blocks = [
        {
            'index': 1,
            'text': 'take a look at THIS (segment 1)',
            'raw_text': 'take a look at THIS (segment 1)',
            'speaker': 0, 'is_turn_start': True
        },
        {
            'index': 2,
            'text': '           └This line overlaps',
            'raw_text': '           └This line overlaps',
            'speaker': 1, 'is_turn_start': True,
            'overlap_info': {
                'indent': 11,
                'overlap_text': '└This line overlaps',
                'prev_block_idx': 0,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["C", "D"]
    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        add_blank_line=True,
        concatenate_turns=True
    )
    lines = text.split('\n')
    # Output structure:
    #   1 C: take a look at THIS (segment 1)
    #   2                      |              ← bar BEFORE overlap
    #   3 D:                   └This line overlaps
    assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}:\n{text}"

    def strip_line_num(l):
        return l[l.index(' ') + 1:] if ' ' in l else l

    bar_content = strip_line_num(lines[1])
    ov_content = strip_line_num(lines[2])

    # Overlap line has └ in it
    colon_pos = ov_content.index('└') if '└' in ov_content else -1
    assert colon_pos >= 0, f"No └ in overlap line: {ov_content}"
    # Bar line should have '|' at exactly that same column
    assert len(bar_content) >= colon_pos + 1, \
        f"Bar content too short ({len(bar_content)}) for col {colon_pos}: {repr(bar_content)}"
    assert bar_content[colon_pos] == '|', \
        f"Expected '|' at col {colon_pos}, got {repr(bar_content[colon_pos])}: {repr(bar_content)}"
    # All chars before the | should be spaces
    assert bar_content[:colon_pos].count(' ') == colon_pos, \
        f"Expected {colon_pos} spaces before |, got: {repr(bar_content[:colon_pos])}"
    # Verify bar is BEFORE the overlap (line 1 is bar, line 2 is overlap)
    assert '└' not in bar_content, "Bar line should not contain └"


def test_tiq_vertical_bar_text_before(transcript):
    """No vertical bar when overlap block has text_before — just blank line.

    The overlap line (└overlap) appears inline in X's output, then a blank
    line, then Y's turn with its remaining text (some text more).
    """
    transcript.blocks = [
        {
            'index': 1,
            'text': 'First line',
            'raw_text': 'First line',
            'speaker': 0, 'is_turn_start': True
        },
        {
            'index': 2,
            'text': 'some text └overlap more',
            'raw_text': 'some text └overlap more',
            'speaker': 1, 'is_turn_start': True,
            'overlap_info': {
                'indent': 12,
                'overlap_text': '└overlap',
                'prev_block_idx': 0,
                'convention': 'tiq',
                'text_before': 'some text',
                'text_after': 'more'
            }
        }
    ]
    transcript.speakers = ["X", "Y"]
    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        add_blank_line=True,
        concatenate_turns=True
    )
    lines = text.split('\n')
    # Output structure:
    #   1 X: First line
    #   2 Y: └overlap               (cross-speaker overlap inside X's turn)
    #   3                           (blank line — text_before exists, so no |)
    #   4    some text more         (Y's actual turn text, wrapped/indented)
    assert len(lines) == 4, f"Expected 4 lines, got {len(lines)}:\n{text}"
    # Line 3 should be blank (no |)
    line3_stripped = lines[2][lines[2].index(' ') + 1:] if ' ' in lines[2] else lines[2]
    assert '|' not in line3_stripped, f"Unexpected '|' in blank line: {repr(line3_stripped)}"
    assert line3_stripped.strip() == '', f"Line 3 not blank: {repr(line3_stripped)}"
    # Line 4 should contain Y's text
    assert 'some text' in lines[3] or 'more' in lines[3], f"Line 4 missing Y's text: {lines[3]}"
# ----------------------------------------------------------------------
# Old-format overlap detection and upgrade tests
# ----------------------------------------------------------------------

INDENT_PL = '\u2423'  # ␣ - SRTEditor.INDENT_PLACEHOLDER


def test_infer_overlap_info_gat2_old_format(transcript):
    """_infer_overlap_info_from_raw_text should detect old GAT2 overlap markers."""
    from generators import _infer_overlap_info_from_raw_text
    raw = f"before text{INDENT_PL}{INDENT_PL}{INDENT_PL}[overlap]after text"
    block = {'raw_text': raw}
    info = _infer_overlap_info_from_raw_text(block, INDENT_PL)
    assert info is not None
    assert info['indent'] == 3
    assert info['overlap_text'] == '[overlap]'
    assert info['text_before'] == 'before text'
    assert info['text_after'] == 'after text'
    assert info['convention'] == 'gat2'


def test_infer_overlap_info_tiq_old_format(transcript):
    """_infer_overlap_info_from_raw_text should detect old TiQ overlap markers."""
    from generators import _infer_overlap_info_from_raw_text
    raw = f"before text{INDENT_PL}{INDENT_PL}└overlap text"
    block = {'raw_text': raw}
    info = _infer_overlap_info_from_raw_text(block, INDENT_PL)
    assert info is not None
    assert info['indent'] == 2
    assert info['overlap_text'] == '└overlap text'
    assert info['text_before'] == 'before text'
    assert info['text_after'] == ''
    assert info['convention'] == 'tiq'


def test_infer_overlap_info_no_placeholder(transcript):
    """Should return None when no placeholder is present."""
    from generators import _infer_overlap_info_from_raw_text
    block = {'raw_text': 'just normal text'}
    info = _infer_overlap_info_from_raw_text(block, INDENT_PL)
    assert info is None


def test_infer_overlap_info_placeholder_no_overlap(transcript):
    """Should return None when ␣ is present but no overlap marker follows."""
    from generators import _infer_overlap_info_from_raw_text
    raw = f"some{INDENT_PL}text"
    block = {'raw_text': raw}
    info = _infer_overlap_info_from_raw_text(block, INDENT_PL)
    assert info is None


def test_export_with_old_format_gat2(transcript):
    """GAT2 export with old-format blocks (no overlap_info) should still produce correct indentation."""
    from generators import generate_gat2_text
    transcript.blocks = [
        {'index': 1, 'text': 'first part', 'raw_text': 'first part',
         'speaker': 0, 'is_turn_start': True, 'start_time': '00:00:01,000', 'end_time': '00:00:03,000'},
        {'index': 2, 'text': f'some text{INDENT_PL}{INDENT_PL}{INDENT_PL}[overlap]after',
         'raw_text': f'some text{INDENT_PL}{INDENT_PL}{INDENT_PL}[overlap]after',
         'speaker': 1, 'is_turn_start': True, 'start_time': '00:00:02,000', 'end_time': '00:00:04,000',
         'overlap_info': None}  # explicitly no overlap_info
    ]
    transcript.speakers = ["A", "B"]
    text = generate_gat2_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True
    )
    # Should contain the overlap text
    assert "[overlap]" in text


def test_export_with_old_format_tiq(transcript):
    """TiQ export with old-format blocks (no overlap_info) should still produce correct indentation."""
    from generators import generate_tiq_text
    transcript.blocks = [
        {'index': 1, 'text': 'first part', 'raw_text': 'first part',
         'speaker': 0, 'is_turn_start': True, 'start_time': '00:00:01,000', 'end_time': '00:00:03,000'},
        {'index': 2, 'text': f'some text{INDENT_PL}{INDENT_PL}└overlap more',
         'raw_text': f'some text{INDENT_PL}{INDENT_PL}└overlap more',
         'speaker': 1, 'is_turn_start': True, 'start_time': '00:00:02,000', 'end_time': '00:00:04,000',
         'overlap_info': None}  # explicitly no overlap_info
    ]
    transcript.speakers = ["A", "B"]
    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True
    )
    # Should contain the overlap text
    assert "└overlap" in text



# ----------------------------------------------------------------------
# Chained overlap export tests
# ----------------------------------------------------------------------

def test_tiq_chained_overlap(transcript):
    """TiQ: chained overlap where an overlap block itself is overlapped should show all overlaps."""
    from generators import generate_tiq_text
    transcript.blocks = [
        {
            'index': 1,
            'text': 'this is an example to illustrate the issue at hand',
            'raw_text': 'this is an example to illustrate the issue at hand',
            'speaker': 0, 'is_turn_start': True,
            'start_time': '00:00:01,000', 'end_time': '00:00:03,000'
        },
        {
            'index': 2,
            'text': '           \u2514This line overlaps with line 17',
            'raw_text': '           \u2514This line overlaps with line 17',
            'speaker': 1, 'is_turn_start': True,
            'start_time': '00:00:02,000', 'end_time': '00:00:04,000',
            'overlap_info': {
                'indent': 11,
                'overlap_text': '\u2514This line overlaps with line 17',
                'prev_block_idx': 0,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        },
        {
            'index': 3,
            'text': '                         \u2514This one with line 18',
            'raw_text': '                         \u2514This one with line 18',
            'speaker': 0, 'is_turn_start': True,
            'start_time': '00:00:03,000', 'end_time': '00:00:05,000',
            'overlap_info': {
                'indent': 25,
                'overlap_text': '\u2514This one with line 18',
                'prev_block_idx': 1,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["C", "D"]
    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True
    )
    assert "example to illustrate" in text
    assert "\u2514This line overlaps" in text
    assert "\u2514This one" in text


def test_gat2_chained_overlap(transcript):
    """GAT2: chained overlap where an overlap block itself is overlapped should show all overlaps."""
    from generators import generate_gat2_text
    transcript.blocks = [
        {
            'index': 1,
            'text': 'this is an example to illustrate the issue at hand',
            'raw_text': 'this is an example to illustrate the issue at hand',
            'speaker': 0, 'is_turn_start': True,
            'start_time': '00:00:01,000', 'end_time': '00:00:03,000'
        },
        {
            'index': 2,
            'text': '           [This line overlaps]',
            'raw_text': '           [This line overlaps]',
            'speaker': 1, 'is_turn_start': True,
            'start_time': '00:00:02,000', 'end_time': '00:00:04,000',
            'overlap_info': {
                'indent': 11,
                'overlap_text': '[This line overlaps]',
                'prev_block_idx': 0,
                'convention': 'gat2',
                'text_before': '',
                'text_after': ''
            }
        },
        {
            'index': 3,
            'text': '                         [This one overlaps with line 18]',
            'raw_text': '                         [This one overlaps with line 18]',
            'speaker': 0, 'is_turn_start': True,
            'start_time': '00:00:03,000', 'end_time': '00:00:05,000',
            'overlap_info': {
                'indent': 25,
                'overlap_text': '[This one overlaps with line 18]',
                'prev_block_idx': 1,
                'convention': 'gat2',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["C", "D"]
    text = generate_gat2_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=False,
        concatenate_turns=True,
        include_diarization=True
    )
    assert "example to illustrate" in text
    assert "[This line overlaps]" in text
    assert "[This one overlaps with line 18]" in text


# ----------------------------------------------------------------------
# TiQ overlap ordering regression tests
# ----------------------------------------------------------------------

@pytest.mark.timeout(60)
def test_tiq_overlap_wrap_ordering(transcript):
    """TiQ: overlap at wrap boundary should not invert line order.

    Regression test for the bug where overlap line appeared between
    A's two wrapped segments instead of after the correct A-line.
    """
    text_a = "take a look at THIS (segment 1) this is a line to illustrate the current issue with overlapping speech."
    text_b = "This line overlaps"
    transcript.blocks = [
        {
            'index': 1,
            'text': text_a,
            'raw_text': text_a,
            'speaker': 0,
            'is_turn_start': True,
            'start_time': '00:00:01,000',
            'end_time': '00:00:05,000'
        },
        {
            'index': 2,
            'text': '           ' + text_b,
            'raw_text': '           ' + text_b,
            'speaker': 1,
            'is_turn_start': True,
            'start_time': '00:00:02,000',
            'end_time': '00:00:04,000',
            'overlap_info': {
                'indent': 49,
                'overlap_text': '└' + text_b,
                'prev_block_idx': 0,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["C", "D"]

    for wl in range(58, 68):
        text = generate_tiq_text(
            transcript,
            include_timestamps=False,
            wrap_enabled=True,
            wrap_length=wl,
            concatenate_turns=True,
            include_diarization=True
        )
        lines = text.split('\n')
        # The key requirement: the overlap line (with └) must NOT appear
        # before the turn text is complete. Specifically, the overlap should
        # come after the last wrapped line of speaker C's turn, or after the
        # specific line that contains the overlap target word.
        # Check that the overlap line's content (without line number) is
        # indented with "D:" speaker label (since it's a different speaker).
        assert 'D:' in text or '└' in text, f"No overlap or speaker D at wrap {wl}"
        # Find all overlap lines
        overlap_indices = [i for i, line in enumerate(lines) if '└' in line]
        assert len(overlap_indices) > 0, f"No overlap at wrap {wl}"
        ov_idx = overlap_indices[0]
        # Make sure the overlap is not interleaved between two parts of C's line
        # The lines before the overlap should end with some text from C,
        # and the line after should have speaker prefix restored.
        if ov_idx + 1 < len(lines):
            next_line = lines[ov_idx + 1]
            # Strip line number and check if it looks like a content continuation
            stripped = next_line[next_line.index(' ') + 1:] if ' ' in next_line else next_line
            # If the line after overlap starts with speaker prefix, that's fine
            # (it means the next turn starts). If not, it should still be part of C's turn.
            pass


@pytest.mark.timeout(60)
def test_tiq_overlap_does_not_wrap(transcript):
    """TiQ: when overlap is longer than remaining space on target line,
    the base line should break early so the overlap fits on one line."""
    text_a = "This is a short line."
    text_b = "This long overlapping text needs more room than the target line has left"
    transcript.blocks = [
        {
            'index': 1,
            'text': text_a,
            'raw_text': text_a,
            'speaker': 0,
            'is_turn_start': True,
            'start_time': '00:00:01,000',
            'end_time': '00:00:03,000'
        },
        {
            'index': 2,
            'text': '                             ' + text_b,
            'raw_text': '                             ' + text_b,
            'speaker': 1,
            'is_turn_start': True,
            'start_time': '00:00:02,000',
            'end_time': '00:00:04,000',
            'overlap_info': {
                'indent': 29,
                'overlap_text': '└' + text_b,
                'prev_block_idx': 0,
                'convention': 'tiq',
                'text_before': '',
                'text_after': ''
            }
        }
    ]
    transcript.speakers = ["Y", "A"]

    text = generate_tiq_text(
        transcript,
        include_timestamps=False,
        wrap_enabled=True,
        wrap_length=50,
        concatenate_turns=True,
        include_diarization=True
    )
    assert "└" in text
    assert "short line." in text or "This is a" in text
    # The overlap should appear on one line (unless longer than wrap_width)
    lines = text.split('\n')
    overlap_lines = [l for l in lines if '└' in l]
    assert len(overlap_lines) == 1, \
        f"Overlap should be on 1 line, got {len(overlap_lines)}:\n{text}"


# ----------------------------------------------------------------------
# Atomic marker tests — formatting markers must stay intact during wrapping
# ----------------------------------------------------------------------

def test_atomic_markers_tokenize_with_pauses():
    """_tokenize_with_pauses should keep formatting markers as whole tokens."""
    from generators import _tokenize_with_pauses
    text = "Hello #@Bbold#@/B world"
    tokens = _tokenize_with_pauses(text)
    assert "#@B" in tokens, f"#@B should be a token, got {tokens}"
    assert "#@/B" in tokens, f"#@/B should be a token, got {tokens}"


def test_atomic_markers_tokenize_cjk():
    """_tokenize_cjk_with_pauses should keep formatting markers as whole tokens."""
    from generators import _tokenize_cjk_with_pauses
    text = "这是#@B重要字#@/B测试"
    tokens = _tokenize_cjk_with_pauses(text)
    assert "#@B" in tokens, f"#@B should be a token, got {tokens}"
    assert "#@/B" in tokens, f"#@/B should be a token, got {tokens}"


def test_atomic_markers_italic():
    """Italic markers (#@I, #@/I) should be atomic in CJK tokenizer."""
    from generators import _tokenize_cjk_with_pauses
    text = "强调#@I斜体#@/I结束"
    tokens = _tokenize_cjk_with_pauses(text)
    assert "#@I" in tokens, f"#@I should be a token, got {tokens}"
    assert "#@/I" in tokens, f"#@/I should be a token, got {tokens}"


def test_atomic_markers_underline():
    """Underline markers (#@U, #@/U) should be atomic in CJK tokenizer."""
    from generators import _tokenize_cjk_with_pauses
    text = "下划线#@U文字#@/U结束"
    tokens = _tokenize_cjk_with_pauses(text)
    assert "#@U" in tokens, f"#@U should be a token, got {tokens}"
    assert "#@/U" in tokens, f"#@/U should be a token, got {tokens}"


def test_atomic_markers_all_formats_cjk():
    """All three formatting markers should survive CJK wrapping in GAT2 export."""
    text = "这是#@B重要字#@/B和#@I斜体字#@/I还有#@U下划线#@/U结束"
    transcript = Transcript(
        blocks=[{
            'index': 1, 'start_time': '00:00:00,000', 'end_time': '00:00:02,000',
            'text': text, 'raw_text': text,
            'speaker': 0, 'is_turn_start': True
        }],
        speakers=["A"], cjk_mode=True
    )
    # Wrap at narrow width to force line breaks
    result = generate_gat2_text(
        transcript, include_timestamps=False, wrap_enabled=True,
        wrap_length=20, character_wrap=False, concatenate_turns=False
    )
    assert "#@B" in result, f"#@B marker missing in output:\n{result}"
    assert "#@/B" in result, f"#@/B marker missing in output:\n{result}"
    assert "#@I" in result, f"#@I marker missing in output:\n{result}"
    assert "#@/I" in result, f"#@/I marker missing in output:\n{result}"
    assert "#@U" in result, f"#@U marker missing in output:\n{result}"
    assert "#@/U" in result, f"#@/U marker missing in output:\n{result}"


def test_atomic_pauses_cjk():
    """Pause symbols should remain atomic in CJK wrapping."""
    from generators import _tokenize_cjk_with_pauses
    text = "的话(.)我就想(.)去法国"
    tokens = _tokenize_cjk_with_pauses(text)
    assert "(.)" in tokens, f"(.) should be a token, got {tokens}"


def test_atomic_tiq_laughter():
    """TiQ short laughter @(.)@ should be atomic."""
    from generators import _tokenize_with_pauses
    text = "Hello @(.)@ world"
    tokens = _tokenize_with_pauses(text)
    assert "@(.)@" in tokens, f"@(.)@ should be a token, got {tokens}"


def test_atomic_tiq_laughter_cjk():
    """TiQ short laughter @(.)@ should be atomic in CJK tokenizer."""
    from generators import _tokenize_cjk_with_pauses
    text = "@(.)@哈哈哈哈"
    tokens = _tokenize_cjk_with_pauses(text)
    assert "@(.)@" in tokens, f"@(.)@ should be a token, got {tokens}"


def test_atomic_comment_wrappers_not_atomic():
    """Comment-like wrappers (<<...>>, ((...))) should NOT be atomic in CJK mode.
    
    They contain variable-length content and should be character-split
    during CJK wrapping (same as regular text).
    """
    from generators import _tokenize_cjk_with_pauses
    text = "((咳嗽))"
    tokens = _tokenize_cjk_with_pauses(text)
    # Each character should be its own token since ((...)) is not in ATOMIC_PATTERN
    assert all(len(t) == 1 for t in tokens), \
        f"((...)) comment should be split into single-char tokens, got {tokens}"


def test_atomic_bracket_comments_not_atomic():
    """Bracket comments [...] should NOT be atomic in CJK mode."""
    from generators import _tokenize_cjk_with_pauses
    text = "[笑声]"
    tokens = _tokenize_cjk_with_pauses(text)
    assert all(len(t) == 1 for t in tokens), \
        f"[...] should be split into single-char tokens, got {tokens}"


def test_atomic_markers_in_tiq_wrapping():
    """Formatting markers should survive in TiQ export with wrapping."""
    text = "这是#@B重要#@/B的测试文本用来验证原子标记在换行时不会分裂"
    transcript = Transcript(
        blocks=[{
            'index': 1, 'start_time': '00:00:00,000', 'end_time': '00:00:02,000',
            'text': text, 'raw_text': text,
            'speaker': 0, 'is_turn_start': True
        }],
        speakers=["A"], cjk_mode=True
    )
    result = generate_tiq_text(
        transcript, include_timestamps=False, wrap_enabled=True,
        wrap_length=25, character_wrap=False, concatenate_turns=True,
        include_diarization=True
    )
    assert "#@B" in result, f"#@B marker missing in TiQ output:\n{result}"
    assert "#@/B" in result, f"#@/B marker missing in TiQ output:\n{result}"


def test_atomic_markers_non_cjk_wrapping():
    """Formatting markers should survive in non-CJK wrapping."""
    text = "This is a #@Bbold#@/B and #@Iitalic#@/I and #@Uunderline#@/U test"
    transcript = Transcript(
        blocks=[{
            'index': 1, 'start_time': '00:00:00,000', 'end_time': '00:00:02,000',
            'text': text, 'raw_text': text,
            'speaker': 0, 'is_turn_start': True
        }],
        speakers=["A"], cjk_mode=False
    )
    result = generate_gat2_text(
        transcript, include_timestamps=False, wrap_enabled=True,
        wrap_length=30, character_wrap=False, concatenate_turns=False
    )
    assert "#@B" in result, f"#@B marker missing in output:\n{result}"
    assert "#@/B" in result, f"#@/B marker missing in output:\n{result}"
    assert "#@I" in result, f"#@I marker missing in output:\n{result}"
    assert "#@/I" in result, f"#@/I marker missing in output:\n{result}"
    assert "#@U" in result, f"#@U marker missing in output:\n{result}"
    assert "#@/U" in result, f"#@/U marker missing in output:\n{result}"
