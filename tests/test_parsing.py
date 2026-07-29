"""Unit tests for parsing various subtitle formats."""
import pytest
import json
from parsers import parse_srt, parse_text, parse_tsv, parse_json, parse_vtt

# ----------------------------------------------------------------------
# Pure parser tests — no Qt, no editor instance needed
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# SRT parsing
# ----------------------------------------------------------------------
def test_parse_srt_basic():
    content = """1
00:00:01,000 --> 00:00:04,000
Hello world

2
00:00:05,000 --> 00:00:07,500
Second line"""
    blocks = parse_srt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Hello world"
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:04,000"
    assert blocks[1]['text'] == "Second line"

def test_parse_srt_malformed():
    content = "1\n00:00:01,000 --> 00:00:04,000"
    blocks = parse_srt(content)
    assert blocks == []

def test_parse_text_basic():
    content = "Line one\nLine two\n\nLine three"
    blocks = parse_text(content)
    assert len(blocks) == 3
    assert blocks[0]['text'] == "Line one"
    assert blocks[1]['text'] == "Line two"
    assert blocks[2]['text'] == "Line three"

def test_parse_tsv_basic():
    content = "start\tend\ttext\n1000\t2000\tHello\n2000\t3000\tWorld"
    blocks = parse_tsv(content)
    assert len(blocks) == 2
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:02,000"
    assert blocks[0]['text'] == "Hello"

def test_parse_json_tokens_format():
    data = {"tokens": ["Hello", " ", "world"], "timestamps": [0.5, 0.6, 0.7]}
    blocks = parse_json(data, import_option="one_block")
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello world"

def test_parse_json_segments_format():
    data = {"segments": [{"start": 1.5, "end": 3.2, "text": "Hello"}]}
    blocks = parse_json(data)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello"
    assert blocks[0]['start_time'] == "00:00:01,500"


# ----------------------------------------------------------------------
# VTT parsing
# ----------------------------------------------------------------------

def test_parse_vtt_basic():
    """Basic WebVTT with WEBVTT header and dot-separated ms."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500
Hello world

00:00:03.000 --> 00:00:04.500
Second line
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Hello world"
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:02,500"
    assert blocks[1]['text'] == "Second line"
    assert speakers == []

def test_parse_vtt_no_header():
    """WebVTT content without the WEBVTT header should still parse."""
    content = """00:00:01.000 --> 00:00:02.500
Hello world
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello world"
    assert speakers == []

def test_parse_vtt_with_cue_settings():
    """VTT cues with settings after the timestamp should be ignored."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500 align:start line:90%
Hello world
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello world"

def test_parse_vtt_comma_separator():
    """VTT with comma-separated milliseconds (non-standard but common)."""
    content = """WEBVTT

00:00:01,000 --> 00:00:02,500
Hello world
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['start_time'] == "00:00:01,000"

def test_parse_vtt_header_only():
    """Only a WEBVTT header with no cues should return empty lists."""
    content = "WEBVTT\n"
    blocks, speakers = parse_vtt(content)
    assert blocks == []
    assert speakers == []

def test_parse_vtt_speaker_prefix():
    """VTT cues with Speaker: text should preserve the prefix (no <v> tag, so speaker is None)."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500
Alice: Hello world

00:00:03.000 --> 00:00:04.500
Bob: Hi there
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Alice: Hello world"
    assert blocks[1]['text'] == "Bob: Hi there"
    # Without <v> tags, speaker prefix stays in text (CLI's _apply_speaker_pattern handles it)
    assert blocks[0]['speaker'] is None
    assert speakers == []


def test_convert_vtt_tags_bold():
    """<b> tags convert to #@B / #@/B markers."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<b>Hello</b> world")
    assert result == "#@BHello#@/B world"
    assert speaker is None

def test_convert_vtt_tags_italic():
    """<i> tags convert to #@I / #@/I markers."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<i>Hello</i>")
    assert result == "#@IHello#@/I"

def test_convert_vtt_tags_underline():
    """<u> tags convert to #@U / #@/U markers."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<u>Hello</u>")
    assert result == "#@UHello#@/U"

def test_convert_vtt_tags_nested():
    """Nested <b><i> tags convert correctly."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<b><i>Hello</i></b>")
    assert result == "#@B#@IHello#@/I#@/B"

def test_convert_vtt_tags_unclosed():
    """Unclosed <b> tag adds opening marker only."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<b>Hello")
    assert result == "#@BHello"

def test_convert_vtt_tags_voice_basic():
    """<v Alice> extracts speaker, strips tag, returns clean text."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<v Alice>Hello world")
    assert result == "Hello world"
    assert speaker == "Alice"

def test_convert_vtt_tags_voice_with_closing():
    """<v Alice>text</v> strips both tags, returns clean text."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<v Alice>Hello world</v>")
    assert result == "Hello world"
    assert speaker == "Alice"

def test_convert_vtt_tags_voice_with_class():
    """<v.loud Bob> ignores voice class, extracts speaker."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<v.loud Bob>Hello")
    assert result == "Hello"
    assert speaker == "Bob"

def test_convert_vtt_tags_voice_multiword_name():
    """Speaker names with spaces are preserved."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<v Alice Smith>Hello</v>")
    assert result == "Hello"
    assert speaker == "Alice Smith"

def test_convert_vtt_tags_class_span_stripped():
    """<c.class> and </c> are stripped."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("Hello <c.highlight>world</c>!")
    assert result == "Hello world!"
    assert speaker is None

def test_convert_vtt_tags_mixed():
    """Voice tag + formatting tags in one cue."""
    from parsers import _convert_vtt_tags
    result, speaker = _convert_vtt_tags("<v Alice><b>Hello</b> world <i>there</i>")
    assert result == "#@BHello#@/B world #@Ithere#@/I"
    assert speaker == "Alice"

def test_parse_vtt_note_blocks_skipped():
    """NOTE blocks are skipped during parsing."""
    content = """WEBVTT

NOTE
This is a comment
about the transcript

00:00:01.000 --> 00:00:02.500
First cue

00:00:03.000 --> 00:00:04.500
Second cue
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "First cue"
    assert blocks[1]['text'] == "Second cue"

def test_parse_vtt_with_voice_tags():
    """Full parse_vtt with <v> speaker diarization tags."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500
<v Alice>Hello world

00:00:03.000 --> 00:00:04.500
<v Bob>Hi there</v>
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Hello world"
    assert blocks[0]['speaker'] == 0
    assert blocks[1]['text'] == "Hi there"
    assert blocks[1]['speaker'] == 1
    assert speakers == ["Alice", "Bob"]

def test_parse_vtt_with_formatting_tags():
    """Full parse_vtt with bold/italic formatting tags."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500
<b>Bold</b> and <i>italic</i> text

00:00:03.000 --> 00:00:04.500
<u>Underlined</u> word
"""
    blocks, speakers = parse_vtt(content)
    assert blocks[0]['text'] == "#@BBold#@/B and #@Iitalic#@/I text"
    assert blocks[1]['text'] == "#@UUnderlined#@/U word"
    assert speakers == []

def test_parse_vtt_note_before_cues():
    """NOTE block before the first cue is skipped."""
    content = """WEBVTT

NOTE
Some metadata here

00:00:01.000 --> 00:00:02.500
First cue
"""
    blocks, speakers = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "First cue"
