"""Stateless file-parsing functions for CapsQual.

All functions are pure — no Qt imports, no UI side-effects.
They take strings/bytes content and return a list of block dicts.
"""

from __future__ import annotations

import re
from typing import Optional


# ── Helper converters ─────────────────────────────────────────────

def ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT time format (HH:MM:SS,mmm)."""
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds (float) to SRT time format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    milliseconds = int((secs - int(secs)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(secs):02d},{milliseconds:03d}"


# ── Auto-segmentation helper (used by parse_json) ─────────────────

def auto_segment_tokens(tokens: list[str],
                         timestamps: list[float]) -> list[dict]:
    """Auto-segment tokens based on pause detection.

    Returns list of dicts with keys ``text``, ``start_time``, ``end_time``
    (SRT-format time strings).
    """
    if len(tokens) != len(timestamps) or len(tokens) < 2:
        return [{'text': ''.join(tokens), 'start_time': '', 'end_time': ''}]

    gaps = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
    avg_gap = sum(gaps) / len(gaps)
    threshold = avg_gap * 2.5

    segments: list[dict] = []
    current_segment: list[str] = []
    current_start = timestamps[0]

    for i, (token, timestamp) in enumerate(zip(tokens, timestamps)):
        current_segment.append(token)
        if i < len(timestamps) - 1:
            gap = timestamps[i + 1] - timestamp
            if gap > threshold:
                segment_text = ''.join(current_segment)
                segments.append({
                    'text': segment_text,
                    'start_time': seconds_to_srt_time(current_start),
                    'end_time': seconds_to_srt_time(timestamp + gap / 2),
                })
                current_segment = []
                if i < len(timestamps) - 1:
                    current_start = timestamps[i + 1]

    if current_segment:
        segment_text = ''.join(current_segment)
        segments.append({
            'text': segment_text,
            'start_time': seconds_to_srt_time(current_start),
            'end_time': seconds_to_srt_time(timestamps[-1] + avg_gap),
        })

    return segments


# ── Parsers ───────────────────────────────────────────────────────

_VTT_TIMESTAMP_RE = re.compile(
    r'(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*'
    r'(\d{2}):(\d{2}):(\d{2})[.,](\d{3})'
)

# Matches WebVTT inline tags: <v Speaker>, <b>, <i>, <u>, <c.class>,
# and their closing counterparts.
_VTT_TAG_RE = re.compile(
    r'<v(?:\.[a-zA-Z][\w-]*)?\s+(?P<voice>[^>]+)>'  # <v SpeakerName>
    r'|</v>'                                           # </v>
    r'|(?P<bold_open><b>)'                             # <b>
    r'|(?P<bold_close></b>)'                           # </b>
    r'|(?P<italic_open><i>)'                           # <i>
    r'|(?P<italic_close></i>)'                         # </i>
    r'|(?P<underline_open><u>)'                        # <u>
    r'|(?P<underline_close></u>)'                      # </u>
    r'|</?c(?:\.[a-zA-Z][\w-]*)?>'                     # <c.class> / </c>
)

# CapsQual internal formatting markers
_VTT_TO_CAPSQUAL = {
    '<b>':  '#@B',   '</b>':  '#@/B',
    '<i>':  '#@I',   '</i>':  '#@/I',
    '<u>':  '#@U',   '</u>':  '#@/U',
}


def _convert_vtt_tags(text: str) -> tuple[str, str | None]:
    """Convert WebVTT inline tags into CapsQual's internal format.

    Returns ``(converted_text, voice_speaker_or_none)``.
    - ``<v SpeakerName>`` → speaker extracted, tag stripped
    - ``<b>`` / ``<i>`` / ``<u>`` → ``#@B`` / ``#@I`` / ``#@U`` markers
    - ``<c.class>`` / ``</c>`` → stripped (class spans not directly supported)
    """
    speaker: str | None = None

    def _sub(m: re.Match) -> str:
        nonlocal speaker
        if m.group('voice'):
            # <v SpeakerName> — extract speaker, strip tag
            speaker = m.group('voice').strip()
            return ''
        if m.group(0) == '</v>':
            return ''
        for raw, marker in _VTT_TO_CAPSQUAL.items():
            if m.group(0) == raw:
                return marker
        # <c.class> or </c> — strip
        return ''

    converted = _VTT_TAG_RE.sub(_sub, text)

    # Collapse multiple spaces caused by tag stripping
    converted = re.sub(r'  +', ' ', converted).strip()

    return converted, speaker


def parse_vtt(content: str) -> tuple[list[dict], list[str]]:
    """Parse WebVTT subtitle content into a list of block dicts and detected speakers.

    Handles standard WebVTT format including inline tags:

    - ``<v SpeakerName>`` voice tags → speaker extracted, assigned to block
    - ``<b>``, ``<i>``, ``<u>`` HTML formatting → ``#@B``, ``#@I``, ``#@U`` markers
    - ``<c.class>`` span tags → stripped
    - ``NOTE`` blocks → skipped

    Returns ``(blocks, vtt_speakers)`` where ``vtt_speakers`` is a list of
    speaker names detected from ``<v>`` tags, in discovery order.
    """
    blocks: list[dict] = []
    vtt_speakers: list[str] = []
    vtt_speaker_map: dict[str, int] = {}
    text = content.strip()

    # Strip the WEBVTT header (first line) if present
    if text.startswith("WEBVTT") or text.startswith("webvtt"):
        first_newline = text.find('\n')
        if first_newline != -1:
            text = text[first_newline:].strip()
        else:
            return [], []  # header only, no cues

    cues = text.split('\n\n')

    for cue in cues:
        lines = cue.strip().split('\n')
        if not lines:
            continue

        # Skip NOTE blocks (first non‑empty line is "NOTE", no timestamp)
        first_non_empty = next((l for l in lines if l.strip()), '')
        if first_non_empty.strip().upper().startswith('NOTE') and '-->' not in first_non_empty:
            continue

        time_line = None
        text_start = 0

        # Find the first line that looks like a timestamp
        for i, line in enumerate(lines):
            line = line.strip()
            if '-->' in line:
                time_line = line
                text_start = i + 1
                break

        if time_line is None:
            continue  # no timestamp in this cue block

        # Parse the timestamp
        m = _VTT_TIMESTAMP_RE.match(time_line)
        if not m:
            continue

        cue_text = '\n'.join(lines[text_start:]).strip() if text_start < len(lines) else ""

        # Convert VTT inline tags → CapsQual markers
        cue_text, vtt_speaker = _convert_vtt_tags(cue_text)

        # Assign speaker from <v> tag
        speaker_idx: int | None = None
        if vtt_speaker:
            if vtt_speaker not in vtt_speaker_map:
                vtt_speaker_map[vtt_speaker] = len(vtt_speakers)
                vtt_speakers.append(vtt_speaker)
            speaker_idx = vtt_speaker_map[vtt_speaker]

        block_data = {
            'index': len(blocks) + 1,
            'start_time':
                f"{m.group(1)}:{m.group(2)}:{m.group(3)},{m.group(4)}",
            'start_ms': int(m.group(4)),
            'end_time':
                f"{m.group(5)}:{m.group(6)}:{m.group(7)},{m.group(8)}",
            'end_ms': int(m.group(8)),
            'text': cue_text,
            'raw_text': cue_text,
            'speaker': speaker_idx,
            'is_turn_start': True,
        }
        blocks.append(block_data)

    return blocks, vtt_speakers


def parse_srt(content: str) -> list[dict]:
    """Parse SRT subtitle content into a list of block dicts."""
    blocks: list[dict] = []
    srt_blocks = content.strip().split('\n\n')

    for block in srt_blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            try:
                index = int(lines[0].strip())
                time_line = lines[1].strip()
                time_match = re.match(
                    r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> '
                    r'(\d{2}):(\d{2}):(\d{2}),(\d{3})',
                    time_line,
                )
                if time_match:
                    text = '\n'.join(lines[2:]).strip()
                    block_data = {
                        'index': index,
                        'start_time':
                            f"{time_match.group(1)}:{time_match.group(2)}:"
                            f"{time_match.group(3)},{time_match.group(4)}",
                        'start_ms': int(time_match.group(4)),
                        'end_time':
                            f"{time_match.group(5)}:{time_match.group(6)}:"
                            f"{time_match.group(7)},{time_match.group(8)}",
                        'end_ms': int(time_match.group(8)),
                        'text': text,
                        'raw_text': text,
                        'speaker': None,
                        'is_turn_start': True,
                    }
                    blocks.append(block_data)
            except ValueError:
                continue

    return blocks


def parse_text(content: str) -> list[dict]:
    """Parse plain-text content — one line = one block."""
    blocks: list[dict] = []
    lines = content.strip().split('\n')

    for i, line in enumerate(lines):
        if line.strip():
            block_data = {
                'index': i + 1,
                'start_time': '',
                'end_time': '',
                'text': line.strip(),
                'raw_text': line.strip(),
                'speaker': None,
                'is_turn_start': True,
            }
            blocks.append(block_data)

    return blocks


def parse_tsv(content: str) -> list[dict]:
    """Parse TSV content (start_ms, end_ms, text columns) into blocks."""
    blocks: list[dict] = []
    lines = content.strip().split('\n')

    for i, line in enumerate(lines):
        if i == 0:  # skip header
            continue
        parts = line.split('\t')
        if len(parts) >= 3:
            start_ms = int(parts[0])
            end_ms = int(parts[1])
            text = parts[2]

            block_data = {
                'index': i,
                'start_time': ms_to_srt_time(start_ms),
                'end_time': ms_to_srt_time(end_ms),
                'text': text,
                'raw_text': text,
                'speaker': None,
                'is_turn_start': True,
            }
            blocks.append(block_data)

    return blocks


def parse_json(content: dict | list,
               import_option: Optional[str] = None) -> list[dict]:
    """Parse JSON transcript data into a list of block dicts.

    Parameters
    ----------
    content:
        Decoded JSON data (dict or list).
    import_option:
        Controls how token/timestamp data is segmented:
        - ``"one_block"`` — merge all tokens into one block
        - ``"tokens"`` — each token gets its own block
        - ``"auto_segment"`` — auto-segment based on pause detection
        - ``None`` / other — defaults to ``"one_block"``

    Returns
    -------
    list[dict]
        A (possibly empty) list of block dicts.

    Raises
    ------
    ValueError
        If the input cannot be interpreted as transcript data.
    """
    blocks: list[dict] = []
    option = import_option or "one_block"

    # ── Whisper-style dict with 'tokens' and 'timestamps' ──────
    if isinstance(content, dict) and 'tokens' in content and 'timestamps' in content:
        tokens = content['tokens']
        timestamps = content['timestamps']

        if option == "one_block":
            text = ''.join(tokens) if tokens else ""
            blocks.append({
                'index': 1,
                'start_time': '',
                'end_time': '',
                'text': text,
                'raw_text': text,
                'speaker': None,
                'is_turn_start': True,
            })

        elif option == "tokens":
            for i, (token, timestamp) in enumerate(zip(tokens, timestamps)):
                blocks.append({
                    'index': i + 1,
                    'start_time': seconds_to_srt_time(timestamp),
                    'end_time': '',
                    'text': token,
                    'raw_text': token,
                    'speaker': None,
                    'is_turn_start': True,
                })

        elif option == "auto_segment":
            segments = auto_segment_tokens(tokens, timestamps)
            for i, segment in enumerate(segments):
                blocks.append({
                    'index': i + 1,
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'text': segment['text'],
                    'raw_text': segment['text'],
                    'speaker': None,
                    'is_turn_start': True,
                })

        return blocks

    # ── Dict with 'segments' key (e.g. WhisX / vosk style) ────
    if isinstance(content, dict) and 'segments' in content:
        for i, segment in enumerate(content['segments']):
            blocks.append({
                'index': i + 1,
                'start_time': seconds_to_srt_time(segment.get('start', 0)),
                'end_time': seconds_to_srt_time(segment.get('end', 0)),
                'text': segment.get('text', '').strip(),
                'raw_text': segment.get('text', '').strip(),
                'speaker': None,
                'is_turn_start': True,
            })
        return blocks

    # ── Simple dict with 'text' key ────────────────────────────
    if isinstance(content, dict) and 'text' in content:
        blocks.append({
            'index': 1,
            'start_time': '',
            'end_time': '',
            'text': content['text'].strip(),
            'raw_text': content['text'].strip(),
            'speaker': None,
            'is_turn_start': True,
        })
        return blocks

    # ── List of items ──────────────────────────────────────────
    if isinstance(content, list):
        for i, item in enumerate(content):
            if isinstance(item, dict):
                blocks.append({
                    'index': i + 1,
                    'start_time': item.get('start_time', ''),
                    'end_time': item.get('end_time', ''),
                    'text': item.get('text', ''),
                    'raw_text': item.get('text', ''),
                    'speaker': None,
                    'is_turn_start': True,
                })
        return blocks

    # ── Dict with generic 'transcript' or 'blocks' sub-key ─────
    if isinstance(content, dict):
        transcript_data = content.get('transcript', content.get('blocks', []))
        if isinstance(transcript_data, list):
            for i, item in enumerate(transcript_data):
                if isinstance(item, dict):
                    blocks.append({
                        'index': i + 1,
                        'start_time': item.get('start_time', ''),
                        'end_time': item.get('end_time', ''),
                        'text': item.get('text', ''),
                        'raw_text': item.get('text', ''),
                        'speaker': None,
                        'is_turn_start': True,
                    })
            return blocks

    # ── Nothing matched ────────────────────────────────────────
    if not blocks:
        raise ValueError(
            "JSON data does not contain recognisable transcript content "
            "(expected 'tokens', 'segments', 'text', or a list)."
        )
    return blocks
