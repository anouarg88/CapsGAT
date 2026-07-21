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
    blocks = parse_vtt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Hello world"
    assert blocks[0]['start_time'] == "00:00:01,000"
    assert blocks[0]['end_time'] == "00:00:02,500"
    assert blocks[1]['text'] == "Second line"

def test_parse_vtt_no_header():
    """WebVTT content without the WEBVTT header should still parse."""
    content = """00:00:01.000 --> 00:00:02.500
Hello world
"""
    blocks = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello world"

def test_parse_vtt_with_cue_settings():
    """VTT cues with settings after the timestamp should be ignored."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500 align:start line:90%
Hello world
"""
    blocks = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['text'] == "Hello world"

def test_parse_vtt_comma_separator():
    """VTT with comma-separated milliseconds (non-standard but common)."""
    content = """WEBVTT

00:00:01,000 --> 00:00:02,500
Hello world
"""
    blocks = parse_vtt(content)
    assert len(blocks) == 1
    assert blocks[0]['start_time'] == "00:00:01,000"

def test_parse_vtt_header_only():
    """Only a WEBVTT header with no cues should return empty list."""
    content = "WEBVTT\n"
    blocks = parse_vtt(content)
    assert blocks == []

def test_parse_vtt_speaker_prefix():
    """VTT cues with Speaker: text should preserve the speaker prefix."""
    content = """WEBVTT

00:00:01.000 --> 00:00:02.500
Alice: Hello world

00:00:03.000 --> 00:00:04.500
Bob: Hi there
"""
    blocks = parse_vtt(content)
    assert len(blocks) == 2
    assert blocks[0]['text'] == "Alice: Hello world"
    assert blocks[1]['text'] == "Bob: Hi there"
    # Speaker is not parsed by parse_vtt itself — that's CLI's job
    assert blocks[0]['speaker'] is None
