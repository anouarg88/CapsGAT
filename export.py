"""Transcript export/generation functions for CapsQual.

Contains all logic for generating transcript text in various formats
(GAT2, Dresing & Pehl, TiQ, SRT) and exporting to file formats
(HTML, DOCX, TXT, SRT).
"""

import os
import re
import json
from pathlib import Path


# ──────────────────────────────────────────────
#  Export helper utilities
# ──────────────────────────────────────────────

def time_to_seconds(time_str):
    """Convert time string to seconds with milliseconds as decimal."""
    if not time_str:
        return 0

    if ',' in time_str:
        time_part, ms_part = time_str.split(',')
        ms = int(ms_part)
    else:
        time_part = time_str
        ms = 0

    parts = time_part.split(':')
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = int(parts[1])
    else:
        return 0

    return hours * 3600 + minutes * 60 + seconds + ms / 1000.0


def time_to_ms(time_str):
    """Convert time string to milliseconds."""
    if not time_str:
        return 0

    if ',' in time_str:
        time_part, ms_part = time_str.split(',')
        ms = int(ms_part)
    else:
        time_part = time_str
        ms = 0

    parts = time_part.split(':')
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = int(parts[1])
    else:
        return 0

    return (hours * 3600 + minutes * 60 + seconds) * 1000 + ms


def format_timestamp(seconds, style="curly", custom_pattern=None):
    """
    Format a timestamp (seconds) according to the chosen style.
    style: "hash", "bracket", "curly", "custom"
    custom_pattern: a string containing placeholders HH, mm, ss, xx (case-insensitive)
    Returns a string (no surrounding whitespace).
    """
    if seconds is None:
        return ""

    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    tenths = int((seconds - int(seconds)) * 10)

    if style == "curly":
        return f"{{{h:02d}:{m:02d}:{s:02d}}}"
    elif style == "hash":
        return f"#{h:02d}:{m:02d}:{s:02d}-{tenths}#"
    elif style == "bracket":
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    elif style == "custom" and custom_pattern:
        result = custom_pattern
        result = re.sub(r'HH', f"{h:02d}", result, flags=re.IGNORECASE)
        result = re.sub(r'MM', f"{m:02d}", result, flags=re.IGNORECASE)
        result = re.sub(r'SS', f"{s:02d}", result, flags=re.IGNORECASE)
        result = re.sub(r'XX', f"{tenths}", result, flags=re.IGNORECASE)
        return result
    else:
        return ""


def get_timestamp_width(style, custom_pattern=None):
    """Return the width (in characters) of a timestamp for the given style."""
    if style == "curly":
        return 10
    elif style == "hash":
        return 12
    elif style == "bracket":
        return 10
    else:  # custom
        sample = format_timestamp(5025.6, style, custom_pattern)
        return len(sample)


def format_srt_time(time_str):
    """Convert time string to SRT format (HH:MM:SS,mmm)."""
    if not time_str:
        return "00:00:00,000"

    if ',' in time_str:
        return time_str
    elif ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 2:
            return f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)},000"
        elif len(parts) == 3:
            time_part = parts[2]
            if ',' in time_part:
                time_part, ms_part = time_part.split(',')
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{time_part.zfill(2)},{ms_part.zfill(3)}"
            else:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{time_part.zfill(2)},000"

    return "00:00:00,000"


def strip_markup(text):
    """Remove formatting markers, leaving only the inner text."""
    text = re.sub(r'#@[BIU](.*?)#@/[BIU]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'#@[BIU]|#@/[BIU]', '', text)
    return text


def escape_html(text):
    """Escape HTML special characters to prevent interpretation as HTML tags."""
    if not text:
        return text
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))


def convert_markup_to_html(text):
    """Convert #@B #@/B, #@I #@/I, #@U #@/U to HTML tags."""
    text = re.sub(r'#@B(.*?)#@/B', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'#@I(.*?)#@/I', r'<i>\1</i>', text, flags=re.DOTALL)
    text = re.sub(r'#@U(.*?)#@/U', r'<u>\1</u>', text, flags=re.DOTALL)
    return text


def replace_indent_placeholders(text, indent_placeholder, cjk_mode=False, for_export=False):
    """Replace indent placeholders with spaces.
    If for_export is True and cjk_mode is True, replace each placeholder with two spaces.
    Otherwise replace with one space.
    """
    if for_export and cjk_mode:
        return text.replace(indent_placeholder, '  ')
    else:
        return text.replace(indent_placeholder, ' ')


# ──────────────────────────────────────────────
#  Transcript generation functions
# ──────────────────────────────────────────────

def generate_gat2_text(
    editor,
    include_timestamps=True,
    timestamp_style="curly",
    custom_pattern=None,
    include_diarization=True,
    wrap_enabled=False,
    wrap_length=80,
    character_wrap=False,
    add_blank_line=False,
    concatenate_turns=False,
    delimiter_choice="default",
    custom_delimiter=""
):
    """Generate GAT2 convention transcript text."""
    if not editor.srt_blocks:
        return ""

    cjk_mode = editor.cjk_mode

    # Determine delimiter
    if delimiter_choice == "default":
        delimiter = " " if not cjk_mode else ""
    elif delimiter_choice == "custom":
        delimiter = custom_delimiter
    else:
        delimiter = " "

    def is_valid_block(b):
        return (b['speaker'] is not None) or b.get('is_pause') or b.get('is_comment')

    if concatenate_turns:
        turns = _group_into_turns(editor, include_timestamps)
        if not turns:
            return ""

        max_speaker_length = 2
        for turn in turns:
            speaker_label = editor.speakers[turn['speaker']] + ":"
            max_speaker_length = max(max_speaker_length, len(speaker_label))

        total_turns = len(turns)
        line_digits = len(str(total_turns))

        if include_timestamps:
            ts_width = get_timestamp_width(timestamp_style, custom_pattern)
            timestamp_padding = " " * (ts_width + 3)
        else:
            timestamp_padding = ""

        output_lines = []

        for turn_idx, turn in enumerate(turns, start=1):
            turn_text = delimiter.join(
                replace_indent_placeholders(b['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).strip()
                for b in turn['blocks'] if b['text'].strip()
            )
            if not turn_text:
                continue

            line_num_part = f"{turn_idx:0{line_digits}d}   "

            if include_timestamps:
                if turn.get('start_time'):
                    seconds = time_to_seconds(turn['start_time'])
                    ts = format_timestamp(seconds, timestamp_style, custom_pattern)
                    timestamp = f"{ts}   "
                else:
                    timestamp = timestamp_padding
            else:
                timestamp = ""

            speaker_part = editor.speakers[turn['speaker']] + ":"
            speaker_part = speaker_part.ljust(max_speaker_length) + "   "
            left_part = timestamp + line_num_part + speaker_part

            if wrap_enabled and wrap_length > 0:
                available_width = wrap_length - len(left_part)
                if available_width < 10:
                    available_width = 40
                lines = _wrap_text(editor, turn_text, available_width, character_wrap, first_line_only_indent=True)
                for idx, line in enumerate(lines):
                    if idx == 0:
                        output_lines.append(left_part + line)
                    else:
                        output_lines.append(' ' * len(left_part) + line)
            else:
                output_lines.append(left_part + turn_text)

            if add_blank_line:
                output_lines.append("")

        return '\n'.join(output_lines)

    else:
        included_blocks = [b for b in editor.srt_blocks if is_valid_block(b)]
        if not included_blocks:
            return ""

        max_speaker_length = 2
        for b in included_blocks:
            if b['speaker'] is not None and b.get('is_turn_start', True):
                speaker_label = editor.speakers[b['speaker']] + ":"
                max_speaker_length = max(max_speaker_length, len(speaker_label))

        total_lines = len(included_blocks)
        line_digits = len(str(total_lines))

        if include_timestamps:
            ts_width = get_timestamp_width(timestamp_style, custom_pattern)
            timestamp_padding = " " * (ts_width + 3)
        else:
            timestamp_padding = ""

        output_lines = []

        for i, block in enumerate(included_blocks):
            line_num = i + 1
            line_number_part = f"{line_num:0{line_digits}d}   "

            if block.get('is_turn_start', True) and block['speaker'] is not None:
                speaker_part = editor.speakers[block['speaker']] + ":"
                speaker_part = speaker_part.ljust(max_speaker_length) + "   "
            else:
                speaker_part = " " * (max_speaker_length + 3)

            if include_timestamps:
                if block.get('is_turn_start', True) and block['speaker'] is not None:
                    if block.get('start_time'):
                        seconds = time_to_seconds(block['start_time'])
                        ts = format_timestamp(seconds, timestamp_style, custom_pattern)
                        timestamp = f"{ts}   "
                    else:
                        timestamp = timestamp_padding
                else:
                    timestamp = timestamp_padding
            else:
                timestamp = ""

            left_part = timestamp + line_number_part + speaker_part
            text = replace_indent_placeholders(block['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)

            if wrap_enabled and wrap_length > 0:
                available_width = wrap_length - len(left_part)
                if available_width < 10:
                    available_width = 40
                lines = _wrap_text(editor, text, available_width, character_wrap, first_line_only_indent=True)
                for idx, line in enumerate(lines):
                    if idx == 0:
                        output_lines.append(left_part + line)
                    else:
                        output_lines.append(' ' * len(left_part) + line)
            else:
                output_lines.append(left_part + text)

            is_last = (i == len(included_blocks) - 1)
            next_block = included_blocks[i+1] if not is_last else None
            if not is_last and next_block and next_block.get('speaker') != block.get('speaker'):
                if add_blank_line:
                    output_lines.append("")

        return '\n'.join(output_lines)


def generate_dresing_pehl_text(
    editor,
    include_timestamps=True,
    timestamp_style="hash",
    custom_pattern=None,
    include_diarization=True,
    add_blank_line=False,
    concatenate_turns=True,
    delimiter_choice="space",
    custom_delimiter=""
):
    """Generate Dresing & Pehl convention transcript text."""
    if not editor.srt_blocks:
        return ""

    cjk_mode = editor.cjk_mode

    if delimiter_choice == "default":
        delimiter = " " if not cjk_mode else ""
    elif delimiter_choice == "custom":
        delimiter = custom_delimiter
    else:
        delimiter = " "

    segments = _build_ordered_segments(editor, include_timestamps)
    output_lines = []
    output_lines.append("")

    for seg in segments:
        if seg['type'] == 'turn':
            turn_text = delimiter.join(
                replace_indent_placeholders(b['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).strip()
                for b in seg['blocks'] if b['text'].strip()
            )
            if not turn_text:
                continue

            if include_diarization:
                line = f"{editor.speakers[seg['speaker']]}: {turn_text}"
            else:
                line = turn_text

            if include_timestamps and seg['start_time']:
                seconds = time_to_seconds(seg['start_time'])
                ts = format_timestamp(seconds, timestamp_style, custom_pattern)
                line += f" {ts}"

            output_lines.append(line)
            if add_blank_line:
                output_lines.append("")

        else:
            block = seg['block']
            if block['speaker'] is None and not block.get('is_pause') and not block.get('is_comment'):
                continue
            if block.get('is_empty'):
                output_lines.append("")
                continue
            text = replace_indent_placeholders(block['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).strip()
            if text:
                output_lines.append(text)
                if add_blank_line:
                    output_lines.append("")

    return '\n'.join(output_lines)


def generate_tiq_text(
    editor,
    include_timestamps=True,
    timestamp_style="hash",
    custom_pattern=None,
    include_diarization=True,
    wrap_enabled=False,
    wrap_length=80,
    character_wrap=False,
    add_blank_line=False,
    concatenate_turns=True,
    delimiter_choice="space",
    custom_delimiter=""
):
    """Generate TiQ convention transcript text."""
    if not editor.srt_blocks:
        return ""

    cjk_mode = editor.cjk_mode

    if delimiter_choice == "default":
        delimiter = " " if not cjk_mode else ""
    elif delimiter_choice == "custom":
        delimiter = custom_delimiter
    else:
        delimiter = " "

    max_speaker_width = 0
    if include_diarization:
        for speaker in editor.speakers:
            label = f"{speaker}: "
            max_speaker_width = max(max_speaker_width, len(label))
    else:
        max_speaker_width = 0

    segments = _build_ordered_segments(editor, include_timestamps)
    content_lines = []

    for seg in segments:
        if seg['type'] == 'turn':
            turn_text = delimiter.join(
                replace_indent_placeholders(b['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)
                for b in seg['blocks'] if b['text'].strip()
            )
            if not turn_text:
                continue

            ts_token = ""
            if include_timestamps and seg.get('start_time'):
                seconds = time_to_seconds(seg['start_time'])
                ts = format_timestamp(seconds, timestamp_style, custom_pattern)
                ts_token = " " + ts

            if include_diarization:
                speaker_prefix = f"{editor.speakers[seg['speaker']]}: ".ljust(max_speaker_width)
            else:
                speaker_prefix = " " * max_speaker_width

            line_num_width = 4
            line_num_padding = line_num_width + 1
            content_width = wrap_length - line_num_padding - len(speaker_prefix)

            if wrap_enabled and wrap_length > 0 and content_width > 10:
                if character_wrap:
                    tokens = list(turn_text)
                elif cjk_mode:
                    tokens = _tokenize_cjk_with_pauses(editor, turn_text)
                else:
                    tokens = _tokenize_with_pauses(editor, turn_text)

                if ts_token:
                    tokens.append(ts_token)

                lines = []
                current_line = ""
                for token in tokens:
                    if not token:
                        continue
                    if len(current_line + token) > content_width:
                        if current_line:
                            lines.append(current_line)
                            current_line = ""
                        if token.isspace():
                            continue
                        if len(token) > content_width:
                            for i in range(0, len(token), content_width):
                                chunk = token[i:i+content_width]
                                if chunk:
                                    if i == 0:
                                        current_line = chunk
                                    else:
                                        lines.append(chunk)
                            current_line = ""
                        else:
                            current_line = token
                    else:
                        current_line += token

                if current_line:
                    lines.append(current_line)

                for idx, line in enumerate(lines):
                    if idx == 0:
                        content_lines.append(speaker_prefix + line)
                    else:
                        content_lines.append(" " * len(speaker_prefix) + line)
            else:
                line = speaker_prefix + turn_text
                if ts_token:
                    line += ts_token
                content_lines.append(line)

            if add_blank_line:
                content_lines.append("")

        else:
            block = seg['block']
            if block['speaker'] is None and not block.get('is_pause') and not block.get('is_comment'):
                continue
            if block.get('is_empty'):
                content_lines.append("")
                continue
            text = replace_indent_placeholders(block['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).strip()
            if not text:
                continue

            speaker_padding = " " * max_speaker_width
            if wrap_enabled and wrap_length > 0:
                line_num_width = 4
                line_num_padding = line_num_width + 1
                content_width = wrap_length - line_num_padding - len(speaker_padding)
                if content_width > 10:
                    if character_wrap:
                        tokens = list(text)
                    elif cjk_mode:
                        tokens = _tokenize_cjk_with_pauses(editor, text)
                    else:
                        tokens = _tokenize_with_pauses(editor, text)

                    lines = []
                    current_line = ""
                    for token in tokens:
                        if not token:
                            continue
                        if len(current_line + token) > content_width:
                            if current_line:
                                lines.append(current_line)
                                current_line = ""
                            if token.isspace():
                                continue
                            if len(token) > content_width:
                                for i in range(0, len(token), content_width):
                                    chunk = token[i:i+content_width]
                                    if chunk:
                                        if i == 0:
                                            current_line = chunk
                                        else:
                                            lines.append(chunk)
                                current_line = ""
                            else:
                                current_line = token
                        else:
                            current_line += token
                    if current_line:
                        lines.append(current_line)

                    for idx, line in enumerate(lines):
                        if idx == 0:
                            content_lines.append(speaker_padding + line)
                        else:
                            content_lines.append(" " * len(speaker_padding) + line)
                else:
                    content_lines.append(speaker_padding + text)
            else:
                content_lines.append(speaker_padding + text)

    total_lines = len(content_lines)
    line_digits = len(str(total_lines))
    output_lines = []
    for idx, line in enumerate(content_lines, start=1):
        line_num = f"{idx:0{line_digits}d}"
        output_lines.append(f"{line_num} {line}")

    return '\n'.join(output_lines)


def generate_srt_text(editor, include_diarization=True, unassigned_handling="skip"):
    """Generate SRT format text with optional diarization."""
    if not editor.file_has_timestamps:
        return ("SRT export requires timestamp information. Original file does not contain timestamps.\n\n"
                "Note: SRT files require precise timing information for each subtitle.")

    blocks_with_timestamps = estimate_missing_timestamps(editor)

    srt_blocks = []
    subtitle_index = 1

    for block in blocks_with_timestamps:
        if block.get('is_pause') or block.get('is_comment') or block.get('is_empty'):
            continue

        if block['speaker'] is None:
            if unassigned_handling == "skip":
                continue
            elif unassigned_handling == "no_label":
                speaker_prefix = ""
            elif unassigned_handling == "unknown":
                speaker_prefix = "Unknown: "
        else:
            speaker_prefix = ""
            if include_diarization:
                speaker_prefix = f"{editor.speakers[block['speaker']]}: "

        cjk_mode = editor.cjk_mode
        formatted = replace_indent_placeholders(block['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).lstrip()
        formatted = strip_markup(formatted)

        start_time = format_srt_time(block['start_time'])
        end_time = format_srt_time(block['end_time'])

        srt_block = f"{subtitle_index}\n{start_time} --> {end_time}\n{speaker_prefix}{formatted}\n"
        srt_blocks.append(srt_block)
        subtitle_index += 1

    return "\n".join(srt_blocks)


def generate_transcript_text(
    editor,
    include_timestamps=True,
    timestamp_style="hash",
    custom_pattern=None,
    convention="gat2",
    include_diarization=True,
    wrap_enabled=False,
    wrap_length=80,
    character_wrap=False,
    add_blank_line=False,
    concatenate_turns=False,
    delimiter_choice="space",
    custom_delimiter=""
):
    """Route to the correct convention-specific generator."""
    if convention == "dresing_pehl":
        return generate_dresing_pehl_text(
            editor, include_timestamps, timestamp_style, custom_pattern, include_diarization,
            add_blank_line, concatenate_turns, delimiter_choice, custom_delimiter)
    elif convention == "tiq":
        return generate_tiq_text(
            editor, include_timestamps, timestamp_style, custom_pattern, include_diarization,
            wrap_enabled, wrap_length, character_wrap, add_blank_line,
            concatenate_turns, delimiter_choice, custom_delimiter)
    else:  # gat2
        return generate_gat2_text(
            editor, include_timestamps, timestamp_style, custom_pattern, include_diarization,
            wrap_enabled, wrap_length, character_wrap, add_blank_line,
            concatenate_turns, delimiter_choice, custom_delimiter)


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────

def _build_ordered_segments(editor, include_timestamps=False):
    """Walk through srt_blocks and return a list of segments in original order."""
    segments = []
    i = 0
    n = len(editor.srt_blocks)
    while i < n:
        block = editor.srt_blocks[i]
        if block['speaker'] is not None:
            speaker = block['speaker']
            turn_blocks = []
            while i < n and editor.srt_blocks[i]['speaker'] == speaker:
                turn_blocks.append(editor.srt_blocks[i])
                i += 1
            segments.append({
                'type': 'turn',
                'speaker': speaker,
                'blocks': turn_blocks,
                'start_time': turn_blocks[0].get('start_time') if include_timestamps else None,
                'end_time': turn_blocks[-1].get('end_time') if include_timestamps else None
            })
        else:
            segments.append({'type': 'special', 'block': block})
            i += 1
    return segments


def _group_into_turns(editor, include_timestamps=False):
    """Group consecutive blocks with the same speaker into turns."""
    turns = []
    current_turn = None
    for block in editor.srt_blocks:
        if block.get('is_pause') or block.get('is_comment') or block.get('is_empty'):
            continue
        if block['speaker'] is None:
            continue

        speaker_idx = block['speaker']
        if current_turn is None or current_turn['speaker'] != speaker_idx or block.get('is_turn_start', True):
            if current_turn is not None:
                turns.append(current_turn)
            current_turn = {
                'speaker': speaker_idx,
                'blocks': [],
                'start_time': block['start_time'] if include_timestamps else None
            }
        current_turn['blocks'].append(block)
        if include_timestamps and block['end_time']:
            current_turn['end_time'] = block['end_time']
    if current_turn is not None:
        turns.append(current_turn)
    return turns


def _tokenize_with_pauses(editor, text):
    """Split text into tokens, keeping pause symbols whole and spaces as separate tokens."""
    tokens = []
    last_end = 0
    for match in editor.pause_pattern.finditer(text):
        start, end = match.span()
        if start > last_end:
            preceding = text[last_end:start]
            parts = re.split(r'(\s+)', preceding)
            tokens.extend([p for p in parts if p])
        tokens.append(match.group())
        last_end = end
    if last_end < len(text):
        remaining = text[last_end:]
        parts = re.split(r'(\s+)', remaining)
        tokens.extend([p for p in parts if p])
    return tokens


def _tokenize_cjk_with_pauses(editor, text):
    """Split CJK text into tokens: either a single character, or a whole pause symbol."""
    tokens = []
    i = 0
    while i < len(text):
        m = editor.pause_pattern.match(text, i)
        if m:
            tokens.append(m.group())
            i = m.end()
        else:
            tokens.append(text[i])
            i += 1
    return tokens


def _wrap_text(editor, text, max_width, character_wrap=False, first_line_only_indent=True):
    """Wrap text to max_width characters.

    - If character_wrap: break at exact character positions.
    - Otherwise, tokenize using _tokenize_with_pauses (keeps pause symbols atomic)
      and then fill lines greedily, dropping leading spaces on new lines.
    """
    if not text or max_width <= 0:
        return [text]

    if character_wrap:
        return [text[i:i+max_width] for i in range(0, len(text), max_width)]

    tokens = _tokenize_with_pauses(editor, text)

    lines = []
    current_line = ''

    for token in tokens:
        if not token:
            continue

        if len(current_line + token) > max_width:
            if current_line:
                lines.append(current_line)
                current_line = ''

            if token.isspace():
                continue

            if len(token) > max_width:
                for i in range(0, len(token), max_width):
                    chunk = token[i:i+max_width]
                    if chunk:
                        if i == 0:
                            current_line = chunk
                        else:
                            lines.append(chunk)
                current_line = ''
            else:
                current_line = token
        else:
            current_line += token

    if current_line:
        lines.append(current_line)

    return lines


def estimate_missing_timestamps(editor):
    """Estimate timestamps for blocks that don't have them."""
    if not editor.srt_blocks:
        return []

    blocks = editor.srt_blocks.copy()

    timestamped_blocks = []
    for i, block in enumerate(blocks):
        if block.get('start_time') and block.get('end_time'):
            timestamped_blocks.append((i, block))

    if not timestamped_blocks:
        return blocks

    segments = []
    last_timestamped_idx = -1

    for i, block in timestamped_blocks:
        if last_timestamped_idx == -1:
            segments.append({
                'start_idx': 0,
                'end_idx': i,
                'start_time': None,
                'end_time': block['start_time'],
                'total_chars': sum(len(b['text']) for b in blocks[0:i])
            })
        else:
            segments.append({
                'start_idx': last_timestamped_idx + 1,
                'end_idx': i,
                'start_time': blocks[last_timestamped_idx]['end_time'],
                'end_time': block['start_time'],
                'total_chars': sum(len(b['text']) for b in blocks[last_timestamped_idx + 1:i])
            })
        last_timestamped_idx = i

    if last_timestamped_idx < len(blocks) - 1:
        last_block = timestamped_blocks[-1][1] if timestamped_blocks else None
        segments.append({
            'start_idx': last_timestamped_idx + 1,
            'end_idx': len(blocks) - 1,
            'start_time': last_block['end_time'] if last_block else None,
            'end_time': None,
            'total_chars': sum(len(b['text']) for b in blocks[last_timestamped_idx + 1:])
        })

    for segment in segments:
        if segment['start_time'] and segment['end_time'] and segment['total_chars'] > 0:
            start_ms = time_to_ms(segment['start_time'])
            end_ms = time_to_ms(segment['end_time'])
            total_duration = end_ms - start_ms

            current_time = start_ms
            for i in range(segment['start_idx'], segment['end_idx'] + 1):
                block = blocks[i]
                if not block.get('start_time') or not block.get('end_time'):
                    block_chars = len(block['text'])
                    if segment['total_chars'] > 0:
                        block_duration = (block_chars / segment['total_chars']) * total_duration
                    else:
                        block_duration = 1000

                    block_duration = max(100, block_duration)

                    block['start_time'] = _ms_to_time(current_time)
                    block['end_time'] = _ms_to_time(current_time + block_duration)
                    current_time += block_duration

    return blocks


def _ms_to_time(ms):
    """Convert milliseconds to SRT time format."""
    hours = int(ms // 3600000)
    ms %= 3600000
    minutes = int(ms // 60000)
    ms %= 60000
    seconds = int(ms // 1000)
    milliseconds = int(ms % 1000)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
