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

        # Build overlap_map for cross-speaker overlaps
        overlap_map = {}
        for turn in turns:
            for b in turn['blocks']:
                info = b.get('overlap_info')
                if not info and editor.INDENT_PLACEHOLDER in b.get('raw_text', ''):
                    info = _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
                if info:
                    tgt = info.get('prev_block_idx')
                    if tgt is not None:
                        tgt_block = editor.srt_blocks[tgt]
                        if tgt_block['speaker'] != turn['speaker']:
                            if tgt not in overlap_map:
                                overlap_map[tgt] = []
                            overlap_map[tgt].append({
                                'overlap_info': info,
                                'overlap_speaker': turn['speaker']
                            })
        def _block_text_gat2(b):
            info = b.get('overlap_info')
            if not info and editor.INDENT_PLACEHOLDER in b.get('raw_text', ''):
                info = _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
            if info:
                bt = replace_indent_placeholders(info.get('text_before', ''), editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)
                at = replace_indent_placeholders(info.get('text_after', ''), editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)
                return (bt + " " + at).strip() or bt or at
            return replace_indent_placeholders(b['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).strip()
        output_lines = []

        for turn_idx, turn in enumerate(turns, start=1):
            # Build full turn text
            parts = []
            for b in turn['blocks']:
                bt = _block_text_gat2(b)
                if bt: parts.append(bt)
            turn_text = delimiter.join(parts) if parts else ""
            
            # Check if any overlaps (cross-speaker or same-speaker) target this turn
            has_overlap = any(
                b.get('overlap_info') or (editor.INDENT_PLACEHOLDER in b.get('raw_text', '') and _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER))
                for b in turn['blocks']
            )
            from_overlap_map = any(editor.srt_blocks.index(b) in overlap_map for b in turn['blocks'])
            
            if not turn_text and not has_overlap and not from_overlap_map:
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

            # Wrap turn text
            wrapped_lines = []
            if turn_text:
                if wrap_enabled and wrap_length > 0:
                    aw = wrap_length - len(left_part)
                    if aw < 10: aw = 40
                    lines = _wrap_text(editor, turn_text, aw, character_wrap, first_line_only_indent=True)                    # ── Overlap-aware line re-break for GAT2 ──
                    # Convert to tuple format for _rebreak_turn_line_for_overlap
                    wrapped_tuples = []
                    tc = 0
                    for line in lines:
                        wrapped_tuples.append((line, tc))
                        tc += len(line)
                    for b in turn['blocks']:
                        bidx_g = editor.srt_blocks.index(b)
                        if bidx_g in overlap_map:
                            for ov in overlap_map[bidx_g]:
                                info = ov['overlap_info']
                                pos = 0
                                for b2 in turn['blocks']:
                                    if b2 is b:
                                        pos += info['indent']
                                        break
                                    t2 = _block_text_gat2(b2)
                                    if t2: pos += len(t2) + 1
                                # Find the line containing this position
                                for li, (lstr, lcum) in enumerate(wrapped_tuples):
                                    line_end = lcum + len(lstr)
                                    if pos < line_end:
                                        col = pos - lcum
                                        ov_len = len(info['overlap_text'])
                                        if col + ov_len > aw and col < line_end - 1:
                                            wrapped_tuples, _ = _rebreak_turn_line_for_overlap(
                                                turn_text, wrapped_tuples, li, pos,
                                                aw, left_part, editor, cjk_mode, delimiter
                                            )
                                        break
                    lines = [t[0] for t in wrapped_tuples]
                    for idx, line in enumerate(lines):
                        if idx == 0:
                            wrapped_lines.append(left_part + line)
                        else:
                            wrapped_lines.append(' ' * len(left_part) + line)
                else:
                    wrapped_lines.append(left_part + turn_text)
            overlaps_after = []
            for b in turn['blocks']:
                bidx = editor.srt_blocks.index(b)
                if bidx in overlap_map:
                    for ov in overlap_map[bidx]:
                        info = ov['overlap_info']
                        pos = 0
                        for b2 in turn['blocks']:
                            if b2 is b:
                                pos += info['indent']
                                break
                            t2 = _block_text_gat2(b2)
                            if t2: pos += len(t2) + (len(delimiter) if pos > 0 else 0)
                        line_idx = len(wrapped_lines) - 1 if wrapped_lines else 0
                        if wrap_enabled and wrapped_lines:
                            line_cum = 0
                            for li, wl in enumerate(wrapped_lines):
                                content = wl[len(left_part):] if li == 0 else wl[len(' ' * len(left_part)):]
                                if pos < line_cum + len(content):
                                    line_idx = li
                                    break
                                line_cum += len(content)
                            else:
                                line_idx = len(wrapped_lines) - 1
                        overlaps_after.append((line_idx, ov))

            # Same-speaker overlaps
            # Same-speaker overlaps
            for b in turn['blocks']:
                if b.get('overlap_info') or (editor.INDENT_PLACEHOLDER in b.get('raw_text', '') and _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)):
                    info = b.get('overlap_info') or _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
                    tgt = info.get('prev_block_idx')
                    if tgt is None or (tgt is not None and editor.srt_blocks[tgt]['speaker'] == turn['speaker']):
                        overlaps_after.append((len(wrapped_lines) - 1 if wrapped_lines else 0,
                                             {'overlap_info': info, 'overlap_speaker': turn['speaker']}))
            # Insert overlaps from bottom up
            overlaps_after.sort(key=lambda x: -x[0])
            seen = set(); filtered = []
            for li, ov in overlaps_after:
                key = id(ov['overlap_info'])
                if key not in seen: seen.add(key); filtered.append((li, ov))
            overlaps_after = filtered

            for line_idx, ov in overlaps_after:
                info = ov['overlap_info']
                osp_speaker = ov['overlap_speaker']
                osp_label = editor.speakers[osp_speaker] + ":"
                osp_label = osp_label.ljust(max_speaker_length) + "   "
                osp_left = timestamp_padding + " " * len(line_num_part) + osp_label

                aw = (wrap_length - len(osp_left)) if (wrap_enabled and wrap_length > 0) else 0
                col = _compute_overlap_export_indent(editor, info, aw, cjk_mode, delimiter)
                ol = " " * col + info['overlap_text']

                insert_count = 0
                if wrap_enabled and wrap_length > 0 and len(ol) + len(osp_left) > wrap_length:
                    fi = len(osp_left) + col
                    ov_lines = _wrap_with_indent(osp_left + ol, wrap_length, fi)
                    for j, ovl in enumerate(ov_lines):
                        wrapped_lines.insert(line_idx + 1 + j, ovl)
                        insert_count += 1
                else:
                    wrapped_lines.insert(line_idx + 1, osp_left + ol)
                    insert_count = 1

                # Restore speaker prefix on continuation-after-overlap line.
                # Only restore if the line was a continuation of the turn text
                # (starts with left_part-length spaces but NOT a speaker label),
                # NOT a continuation produced by wrap_with_indent for the overlap.
                if insert_count > 0:
                    next_idx = line_idx + insert_count + 1
                    if next_idx < len(wrapped_lines):
                        nxt = wrapped_lines[next_idx]
                        if nxt.startswith(' ' * len(left_part)):
                            rest = nxt[len(left_part):].lstrip()
                            if rest and not any(rest.startswith(s) for s in editor.speakers):
                                wrapped_lines[next_idx] = left_part + nxt[len(left_part):]

            output_lines.extend(wrapped_lines)

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


def _build_ordered_segments(editor, include_timestamps=False):
    """Build ordered segments from srt_blocks, grouping consecutive same-speaker blocks into turns.
    
    Returns a list of segments, each with:
    - type: 'turn' for speaker turns, 'other' for pause/comment/unassigned blocks
    - For turns: speaker, blocks (list), start_time
    - For others: block (single block)
    """
    segments = []
    current_turn = None
    
    for block in editor.srt_blocks:
        speaker = block.get('speaker')
        
        # Skip unassigned blocks that aren't pause/comment
        if speaker is None and not block.get('is_pause') and not block.get('is_comment'):
            continue
        
        if speaker is not None:
            # Speaker block — group into turns
            if current_turn is None or current_turn['speaker'] != speaker or block.get('is_turn_start', True):
                if current_turn is not None:
                    segments.append(current_turn)
                current_turn = {
                    'type': 'turn',
                    'speaker': speaker,
                    'blocks': [],
                    'start_time': block.get('start_time') if include_timestamps else None
                }
            current_turn['blocks'].append(block)
        else:
            # Non-speaker block (pause/comment) — flush current turn and emit as separate segment
            if current_turn is not None:
                segments.append(current_turn)
                current_turn = None
            segments.append({
                'type': 'other',
                'block': block
            })
    
    if current_turn is not None:
        segments.append(current_turn)
    
    return segments




def _rebreak_turn_line_for_overlap(turn_text, wrapped_lines, line_idx, overlap_col,
                                    max_width, prefix, editor, cjk_mode, delimiter):
    """Push content after overlap_col to next line to give overlap room.
    
    Only modifies the line at line_idx by splitting its content at overlap_col.
    Returns (new_wrapped_lines, delta) where delta is 1 if a new line was added.
    """
    if line_idx >= len(wrapped_lines):
        return wrapped_lines, 0
    
    line_str, cum_start = wrapped_lines[line_idx]
    # Get the raw content of this line (strip speaker prefix on first line)
    if line_idx == 0:
        content = line_str[len(prefix):]
    else:
        content = line_str[len(prefix):]  # continuation lines also start with spaces
    
    # Find content length that fits before the overlap column
    # overlap_col is in turn_text chars from cum_start
    # We need to find the position in 'content' that corresponds to overlap_col
    # Simple approach: just take overlap_col chars from the content
    col_in_line = overlap_col - cum_start
    if col_in_line <= 0 or col_in_line >= len(content):
        return wrapped_lines, 0
    
    # Split: first part up to overlap_col, second part the rest
    first_part = content[:col_in_line].rstrip()
    second_part = content[col_in_line:].lstrip()
    
    if not second_part:
        return wrapped_lines, 0
    
    # First line gets the shortened content
    first_prefix = prefix if line_idx == 0 else " " * len(prefix)
    new_line_0 = first_prefix + first_part
    new_line_1 = " " * len(prefix) + second_part
    
    # Build new lines
    result = []
    for i in range(line_idx):
        result.append(wrapped_lines[i])
    result.append((new_line_0, cum_start))
    result.append((new_line_1, cum_start + len(first_part)))
    for i in range(line_idx + 1, len(wrapped_lines)):
        result.append(wrapped_lines[i])
    
    return result, 1


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

    # Build all blocks as flat list with their segment info
    all_segments = _build_ordered_segments(editor, include_timestamps)
    
    # First pass: collect all overlaps pointing at other speakers' turns
    # overlap_map: { target_block_idx: [overlap_info, ...] }
    overlap_map = {}
    for seg in all_segments:
        if seg['type'] == 'turn':
            for b in seg['blocks']:
                info = b.get('overlap_info')
                if not info and editor.INDENT_PLACEHOLDER in b.get('raw_text', ''):
                    info = _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
                if info:
                    tgt = info.get('prev_block_idx')
                    if tgt is not None:
                        # Check if target is in a different speaker's turn
                        tgt_block = editor.srt_blocks[tgt]
                        if tgt_block['speaker'] != seg['speaker']:
                            if tgt not in overlap_map:
                                overlap_map[tgt] = []
                            overlap_map[tgt].append({
                                'overlap_info': info,
                                'overlap_speaker': seg['speaker'],
                                'overlap_block': b
                            })
    # Second pass: walk ALL blocks, find overlap targets anywhere in the list,
    # and emit turns with interleaved overlaps
    line_num_width = 4
    line_num_padding = line_num_width + 1
    content_lines = []
    
    def _speaker_prefix(speaker_idx):
        if include_diarization and speaker_idx is not None:
            return f"{editor.speakers[speaker_idx]}: ".ljust(max_speaker_width)
        return " " * max_speaker_width
    
    def _emit_turn_text(text, prefix, ts=None):
        if not text: return
        cw = wrap_length - line_num_padding - len(prefix) if wrap_length > 0 else 0
        ts_str = ""
        if ts and include_timestamps:
            ts_str = " " + format_timestamp(ts, timestamp_style, custom_pattern)
        if wrap_enabled and cw > 10:
            if character_wrap: tokens = list(text)
            elif cjk_mode: tokens = _tokenize_cjk_with_pauses(editor, text)
            else: tokens = _tokenize_with_pauses(editor, text)
            if ts_str: tokens.append(ts_str)
            lines = []; cl = ""
            for token in tokens:
                if not token: continue
                if len(cl + token) > cw:
                    if cl: lines.append(cl); cl = ""
                    if token.isspace(): continue
                    if len(token) > cw:
                        for j in range(0, len(token), cw):
                            ch = token[j:j+cw]
                            if ch:
                                if j == 0: cl = ch
                                else: lines.append(ch)
                        cl = ""
                    else: cl = token
                else: cl += token
            if cl: lines.append(cl)
            for idx, line in enumerate(lines):
                content_lines.append((prefix + line) if idx == 0 else (" " * len(prefix) + line))
        else:
            content_lines.append(prefix + text + ts_str)
    
    def _emit_overlap_line(info, speaker_idx, prefix, cw):
        col = _compute_overlap_export_indent(editor, info, cw if (wrap_enabled and cw > 10) else 0, cjk_mode, delimiter)
        osp = _speaker_prefix(speaker_idx)
        ol = " " * col + info['overlap_text']
        if wrap_enabled and cw > 10:
            fi = len(osp) + col
            if len(ol) + len(osp) > cw:
                for wl in _wrap_with_indent(osp + ol, wrap_length - line_num_padding, fi):
                    content_lines.append(wl)
            else:
                content_lines.append(osp + ol)
        else:
            content_lines.append(osp + ol)
    
    def _block_text(b):
        """Get exportable text for a block, excluding overlap portion."""
        info = b.get('overlap_info')
        if not info and editor.INDENT_PLACEHOLDER in b.get('raw_text', ''):
            info = _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
        if info:
            bt = replace_indent_placeholders(info.get('text_before', ''), editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)
            at = replace_indent_placeholders(info.get('text_after', ''), editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)
            return (bt + " " + at).strip() or bt or at
        return replace_indent_placeholders(b['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True)
    # Store wrapped lines per first-block-index for overlap column calculation
    _turn_wrapped_map = {}
    def _emit_one_turn(speaker, blocks, start_time):
        """Emit a turn with overlaps interleaved between wrapped lines."""
        if not blocks: return
        prefix = _speaker_prefix(speaker)
        cw = wrap_length - line_num_padding - len(prefix) if wrap_length > 0 else 0

        parts = []
        for b in blocks:
            bt = _block_text(b).strip()
            if bt: parts.append(bt)
        turn_text = delimiter.join(parts) if parts else ""
        
        # Check if there are any overlaps targeting this turn
        # (cross-speaker overlaps from overlap_map)
        has_overlap_target = False
        for b in blocks:
            bidx = editor.srt_blocks.index(b)
            if bidx in overlap_map:
                has_overlap_target = True
                break
        # Also check same-speaker overlaps (blocks whose overlap targets are in same turn)
        if not has_overlap_target:
            for b in blocks:
                info = b.get('overlap_info')
                if not info and editor.INDENT_PLACEHOLDER in b.get('raw_text', ''):
                    info = _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
                if info:
                    tgt = info.get('prev_block_idx')
                    if tgt is None or (tgt is not None and editor.srt_blocks[tgt]['speaker'] == speaker):
                        has_overlap_target = True
                        break
        
        if not turn_text and not has_overlap_target:
            return
        ts = time_to_seconds(start_time) if start_time and include_timestamps else None

        # Wrap the turn text and track character positions at each line        # Wrap the turn text and track character positions at each line
        wrapped_lines = []  # (line_str, cumulative_char_pos_start)
        cw_actual = cw if (wrap_enabled and cw > 10) else 0
        ts_str = ""
        if ts and include_timestamps:
            ts_str = " " + format_timestamp(ts, timestamp_style, custom_pattern)

        # ── Collect overlap targets for this turn ──
        overlap_targets = []  # (char_pos_in_turn_text, overlap_text_len, speaker_idx)
        for b in blocks:
            bidx = editor.srt_blocks.index(b)
            if bidx in overlap_map:
                for ov in overlap_map[bidx]:
                    info = ov['overlap_info']
                    pos = 0
                    for b2 in blocks:
                        if b2 is b:
                            pos += info['indent']
                            break
                        t2 = _block_text(b2).strip()
                        if t2:
                            pos += len(t2) + (len(delimiter) if pos > 0 else 0)
                    overlap_targets.append((pos, len(info['overlap_text']), ov['overlap_speaker']))
        for b in blocks:
            info = b.get('overlap_info')
            if not info and editor.INDENT_PLACEHOLDER in b.get('raw_text', ''):
                info = _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
            if info:
                tgt = info.get('prev_block_idx')
                if tgt is None or (tgt is not None and editor.srt_blocks[tgt]['speaker'] == speaker):
                    pos = 0
                    for b2 in blocks:
                        if b2 is b:
                            pos += info['indent']
                            break
                        t2 = _block_text(b2).strip()
                        if t2:
                            pos += len(t2) + (len(delimiter) if pos > 0 else 0)
                    overlap_targets.append((pos, len(info['overlap_text']), speaker))
        overlap_targets.sort(key=lambda x: x[0])

        if cw_actual and turn_text:
            if character_wrap: tokens = list(turn_text)
            elif cjk_mode: tokens = _tokenize_cjk_with_pauses(editor, turn_text)
            else: tokens = _tokenize_with_pauses(editor, turn_text)
            if ts_str: tokens.append(ts_str)
            cl = ""; cum = 0; ov_ptr = 0

            def _flush_line(text, start):
                nonlocal cum
                is_first = len(wrapped_lines) == 0
                wrapped_lines.append(
                    (prefix + text if is_first else " " * len(prefix) + text, start)
                )
                cum = start + len(text)

            for token in tokens:
                if not token: continue
                # ── Overlap-aware check ──
                proposed_cum = cum + len(cl)
                proposed_end = proposed_cum + len(token)
                must_break = False
                saved_ov_ptr = ov_ptr
                while ov_ptr < len(overlap_targets):
                    ov_pos, ov_len, _ = overlap_targets[ov_ptr]
                    if ov_pos < cum:
                        ov_ptr += 1
                        continue
                    if ov_pos > proposed_end:
                        break
                    col_in_line = ov_pos - cum
                    if col_in_line + ov_len + len(prefix) >= cw_actual:
                        must_break = True
                        break
                    ov_ptr += 1
                if not must_break:
                    ov_ptr = saved_ov_ptr

                if must_break:
                    if cl:
                        _flush_line(cl, cum)
                        cl = ""
                    if token.isspace():
                        continue
                    if len(token) > cw_actual:
                        for j in range(0, len(token), cw_actual):
                            ch = token[j:j+cw_actual]
                            if ch:
                                if j == 0: cl = ch
                                else:
                                    _flush_line(cl, cum)
                                    cl = ch
                        cl = ""
                    else:
                        cl = token
                    continue

                # Normal greedy line-filling
                if len(cl + token) > cw_actual:
                    if cl:
                        _flush_line(cl, cum)
                        cl = ""
                    if token.isspace(): continue
                    if len(token) > cw_actual:
                        for j in range(0, len(token), cw_actual):
                            ch = token[j:j+cw_actual]
                            if ch:
                                if j == 0: cl = ch
                                else:
                                    is_first = len(wrapped_lines) == 0
                                    wrapped_lines.append((prefix + ch if is_first else " " * len(prefix) + ch, cum))
                                    cum += len(ch)
                        cl = ""
                    else: cl = token
                else: cl += token
            if cl:
                _flush_line(cl, cum)
        elif turn_text:
            wrapped_lines.append((prefix + turn_text + ts_str, 0))
        # ── End of overlap-aware wrapping ──
        # Save wrapped line data for overlap column calculation by subsequent turns
        # (do this BEFORE overlap insertion so the column is available to other turns)
        if blocks:
            first_block = blocks[0]
            first_idx = editor.srt_blocks.index(first_block)
            prefix_len = len(prefix)
            pre_lines = []
            pc = 0
            for line_str, cum_start in wrapped_lines:
                content_part = line_str[prefix_len:] if line_str.startswith(prefix) else line_str
                pre_lines.append((content_part, pc))
                pc += len(content_part)
            _turn_wrapped_map[first_idx] = pre_lines

        # Collect overlaps targeting blocks in this turn, finding the line to insert after        # Collect overlaps targeting blocks in this turn, finding the line to insert after
        overlaps_after_line = []  # (line_index, overlap_info)
        for b in blocks:
            bidx = editor.srt_blocks.index(b)
            if bidx in overlap_map:
                for ov in overlap_map[bidx]:
                    info = ov['overlap_info']
                    # Find char position of overlap in raw turn_text
                    pos = 0
                    for b2 in blocks:
                        if b2 is b:
                            pos += info['indent']
                            break
                        t2 = _block_text(b2).strip()
                        if t2: pos += len(t2) + (len(delimiter) if pos > 0 else 0)
                    # Find which wrapped line contains this position.
                    # If pos is at the exact start of a line (boundary), it belongs
                    # to the previous line (overlap is between line-end and line-start).
                    line_idx = 0
                    if wrapped_lines:
                        for li, (_, cum_start) in enumerate(wrapped_lines):
                            if li + 1 < len(wrapped_lines):
                                line_end = wrapped_lines[li + 1][1]
                            else:
                                line_end = len(turn_text)
                            if pos == cum_start:
                                # Position at start of a line -> belongs to this line at col 0
                                line_idx = li
                                break
                            if pos < line_end:
                                line_idx = li
                                break
                        else:
                            line_idx = len(wrapped_lines) - 1
                    overlaps_after_line.append((line_idx, pos, ov))

         # Insert overlaps starting from the bottom so indices stay valid
        overlaps_after_line.sort(key=lambda x: -x[0])
        seen = set()
        filtered = []
        for li, pos, ov in overlaps_after_line:
            key = id(ov['overlap_info'])
            if key not in seen:
                seen.add(key)
                filtered.append((li, pos, ov))
        overlaps_after_line = filtered

        # Same-speaker overlaps go at end
        for b in blocks:
            if b.get('overlap_info') or (editor.INDENT_PLACEHOLDER in b.get('raw_text', '') and _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)):
                info = b.get('overlap_info') or _infer_overlap_info_from_raw_text(b, editor.INDENT_PLACEHOLDER)
                tgt = info.get('prev_block_idx')
                if tgt is None or (tgt is not None and editor.srt_blocks[tgt]['speaker'] == speaker and b['speaker'] == speaker):
                    insert_at = max(0, len(wrapped_lines) - 1)
                    overlaps_after_line.append((insert_at, 0, {'overlap_info': info, 'overlap_speaker': speaker}))

        overlaps_after_line.sort(key=lambda x: -x[0])

        # Track chain overlap sources so we can clean up overlap_map after
        # (preventing re-emission when the source block's turn is processed).
        _chain_overlap_sources = set()
        
        for line_idx, overlap_pos, ov in overlaps_after_line:
            info = ov['overlap_info']
            osp = _speaker_prefix(ov['overlap_speaker'])
            # Compute overlap column directly from wrapped_lines
            col = 0
            if wrapped_lines and line_idx < len(wrapped_lines):
                lstr, lcum = wrapped_lines[line_idx]
                content = lstr[len(prefix):] if lstr.startswith(prefix) else lstr
                content_len = len(content)
                if overlap_pos >= lcum and overlap_pos < lcum + content_len:
                    col = overlap_pos - lcum
                elif overlap_pos == lcum + content_len:
                    col = 0  # at line-end boundary
            # Fallback: when column can't be resolved from wrapped_lines
            # (e.g., target block has no base text = 100% overlap block),
            # use _compute_overlap_export_indent which handles this case.
            if col == 0 and overlap_pos > 0 and (not wrapped_lines or overlap_pos >= (wrapped_lines[-1][1] + len(wrapped_lines[-1][0]))):
                fcol = _compute_overlap_export_indent(editor, info, cw_actual, cjk_mode, delimiter)
                if fcol > 0:
                    col = fcol
            ol = " " * col + info['overlap_text']
            insert_count = 0
            if cw_actual and len(ol) + len(osp) > cw_actual:
                fi = len(osp) + col
                ov_lines = _wrap_with_indent(osp + ol, cw_actual, fi)
                for j, ovl in enumerate(ov_lines):
                    wrapped_lines.insert(line_idx + 1 + j, (ovl, 0))
                    insert_count += 1
            else:
                wrapped_lines.insert(line_idx + 1, (osp + ol, 0))
                insert_count = 1
            
            # ── Chain overlap handling ──
            # After inserting a cross-speaker overlap line, check if the overlap's
            # source block has its own chain overlaps (other overlaps targeting it).
            # This handles the case where e.g., A overlaps D's overlap line.
            source_block = ov.get('overlap_block')
            if source_block is not None:
                src_idx = editor.srt_blocks.index(source_block)
                if src_idx in overlap_map:
                    # Iterate over a copy since we may delete from overlap_map
                    for chain_ov in list(overlap_map[src_idx]):
                        _chain_overlap_sources.add(src_idx)
                        chain_info = chain_ov['overlap_info']
                        # Skip if already processed (dedup by id)
                        chain_key = id(chain_info)
                        if chain_key in seen:
                            continue
                        seen.add(chain_key)
                        chain_osp = _speaker_prefix(chain_ov['overlap_speaker'])
                        # Compute chain overlap column relative to the parent
                        # overlap line's export column (col). The chain indent
                        # includes the parent's own leading ␣ chars and └,
                        # so subtract them to get the offset within the
                        # parent's overlap text content.
                        parent_info = info
                        parent_indent = parent_info.get('indent', 0)
                        # Account for the parent's └ (or [) marker character
                        parent_marker = 1 if parent_info.get('overlap_text', '').startswith(('└', '[')) else 0
                        relative_offset = max(0, chain_info['indent'] - parent_indent - parent_marker)
                        chain_col = col + relative_offset
                        chain_ol_text = " " * chain_col + chain_info['overlap_text']
                        chain_insert_at = line_idx + insert_count + 1
                        if cw_actual and len(chain_ol_text) + len(chain_osp) > cw_actual:
                            chain_fi = len(chain_osp) + chain_col
                            chain_ov_lines = _wrap_with_indent(
                                chain_osp + chain_ol_text, cw_actual, chain_fi
                            )
                            for jj, covl in enumerate(chain_ov_lines):
                                wrapped_lines.insert(chain_insert_at + jj, (covl, 0))
                            insert_count += len(chain_ov_lines)
                        else:
                            wrapped_lines.insert(chain_insert_at, (chain_osp + chain_ol_text, 0))
                            insert_count += 1
            # ── End chain overlap handling ──
            
            # Restore speaker prefix on the continuation line that now follows the overlap.
            # But only if it was a turn-text continuation (starts with prefix-length spaces
            # and isn't a speaker-labeled line from the overlap itself).
            next_idx = line_idx + insert_count + 1
            if next_idx < len(wrapped_lines):
                nxt_str = wrapped_lines[next_idx][0]
                if nxt_str.startswith(" " * len(prefix)):
                    rest = nxt_str[len(prefix):].lstrip()
                    if rest and not any(rest.startswith(s) for s in editor.speakers):
                        wrapped_lines[next_idx] = (prefix + nxt_str[len(prefix):], wrapped_lines[next_idx][1])
        
        # Remove chain overlap sources from overlap_map so they aren't
        # re-emitted when the source block's own turn is processed.
        for src_idx in _chain_overlap_sources:
            if src_idx in overlap_map:
                del overlap_map[src_idx]
        
        for line_str, _ in wrapped_lines:
            content_lines.append(line_str)
    # Walk all segments and emit turn-by-turn with interleaved overlaps
    for i, seg in enumerate(all_segments):
        if seg['type'] == 'turn':
            _emit_one_turn(seg['speaker'], seg['blocks'], seg.get('start_time'))
            # Add blank line / vertical bar between turns when requested
            if add_blank_line and i + 1 < len(all_segments):
                next_seg = all_segments[i + 1]
                if next_seg['type'] == 'turn':
                    first_blk = next_seg['blocks'][0]
                    info = first_blk.get('overlap_info')
                    if not info and editor.INDENT_PLACEHOLDER in first_blk.get('raw_text', ''):
                        info = _infer_overlap_info_from_raw_text(first_blk, editor.INDENT_PLACEHOLDER)
                    if info and not info.get('text_before', '').strip():
                        # Pure overlap: find └ column from the actual emitted overlap line
                        # and insert the bar BEFORE that line
                        next_prefix = _speaker_prefix(next_seg['speaker'])
                        bar_col = 0
                        overlap_idx = None
                        for ci, cl in enumerate(content_lines):
                            if '└' in cl and cl.startswith(next_prefix):
                                bar_col = cl.index('└')
                                overlap_idx = ci
                                break
                        if overlap_idx is not None:
                            content_lines.insert(overlap_idx, ' ' * bar_col + '|')
                        else:
                            content_lines.append(' ' * bar_col + '|')
                    else:
                        content_lines.append('')
                else:
                    content_lines.append('')
        elif seg['type'] == 'other':
            block = seg['block']
            if block.get('is_empty'):
                content_lines.append(""); continue
            text = replace_indent_placeholders(block['raw_text'], editor.INDENT_PLACEHOLDER, cjk_mode, for_export=True).strip()
            if text:
                sp = " " * max_speaker_width
                if wrap_enabled and wrap_length > 0:
                    cw2 = wrap_length - line_num_padding - len(sp)
                    if cw2 > 10:
                        if character_wrap: tokens = list(text)
                        elif cjk_mode: tokens = _tokenize_cjk_with_pauses(editor, text)
                        else: tokens = _tokenize_with_pauses(editor, text)
                        lines = []; cl = ""
                        for token in tokens:
                            if not token: continue
                            if len(cl + token) > cw2:
                                if cl: lines.append(cl); cl = ""
                                if token.isspace(): continue
                                if len(token) > cw2:
                                    for j in range(0, len(token), cw2):
                                        ch = token[j:j+cw2]
                                        if ch:
                                            if j == 0: cl = ch
                                            else: lines.append(ch)
                                    cl = ""
                                else: cl = token
                            else: cl += token
                        if cl: lines.append(cl)
                        for idx, line in enumerate(lines):
                            content_lines.append((sp + line) if idx == 0 else (" " * len(sp) + line))
                    else:
                        content_lines.append(sp + text)
                else:
                    content_lines.append(sp + text)
    
    # Build line-numbered output
    total_lines = len(content_lines)
    line_digits = len(str(total_lines)) if total_lines > 0 else 1
    output_lines = []
    for idx, line in enumerate(content_lines):
        line_num = idx + 1
        output_lines.append(f"{line_num:0{line_digits}d} {line}")
    
    return '\n'.join(output_lines)

def _group_into_turns(editor, include_timestamps=False):
    """Group consecutive blocks with the same speaker into turns."""
    turns = []
    current_turn = None
    for block in editor.srt_blocks:
        # Skip pause/comment/empty blocks, but NEVER skip blocks with overlap_info
        if not block.get('overlap_info') and (block.get('is_pause') or block.get('is_comment') or block.get('is_empty')):
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




def _find_overlap_column(turn_text, char_pos, max_width, editor, cjk_mode, delimiter):
    """Find the column position in wrapped output for a character position in turn text.
    
    Returns the column number (0-based from left margin) where overlap should be placed.
    If wrapping is disabled or max_width <= 0, uses raw character position.
    """
    if not max_width or max_width <= 0:
        return char_pos
    
    if cjk_mode:
        tokens = _tokenize_cjk_with_pauses(editor, turn_text)
    else:
        tokens = _tokenize_with_pauses(editor, turn_text)
    
    lines = []
    line_starts = [0]  # cumulative char position at start of each line
    current_line = ""
    
    for token in tokens:
        if not token:
            continue
        if len(current_line + token) > max_width:
            if current_line:
                lines.append(current_line)
                line_starts.append(line_starts[-1] + len(current_line))
                current_line = ""
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
                            line_starts.append(line_starts[-1] + len(chunk))
                current_line = ""
            else:
                current_line = token
        else:
            current_line += token
    
    if current_line:
        lines.append(current_line)
    
    # Find which line contains char_pos
    line_idx = 0
    for i in range(len(line_starts) - 1, -1, -1):
        if char_pos >= line_starts[i]:
            line_idx = i
            break
    
    col_in_line = char_pos - line_starts[line_idx]
    return col_in_line


def _compute_overlap_export_indent(editor, overlap_info, max_width, cjk_mode, delimiter,
                                    pre_wrapped_lines=None):
    """Compute the wrapping-aware column for an overlap line at export time.
    
    If pre_wrapped_lines is provided, it's a list of (line_str, cum_start) tuples
    from the already-wrapped turn text, and we use its structure instead of
    re-wrapping from scratch. This is needed when the wrapping was modified
    (e.g., overlap-aware re-breaks) so the column matches the actual output.
    """
    prev_block_idx = overlap_info.get('prev_block_idx')
    if prev_block_idx is None:
        return overlap_info.get('indent', 0)
    
    prev_block = editor.srt_blocks[prev_block_idx]
    prev_speaker = prev_block['speaker']
    # Build the previous speaker's full turn text
    turn_blocks = []
    i = prev_block_idx
    while i >= 0 and editor.srt_blocks[i]['speaker'] == prev_speaker:
        turn_blocks.insert(0, editor.srt_blocks[i])
        if editor.srt_blocks[i].get('is_turn_start', False):
            break
        i -= 1
    i = prev_block_idx + 1
    while i < len(editor.srt_blocks) and editor.srt_blocks[i]['speaker'] == prev_speaker:
        if editor.srt_blocks[i].get('is_turn_start', False):
            break
        turn_blocks.append(editor.srt_blocks[i])
        i += 1
    
    # Build turn text and find overlap position
    turn_parts = []
    overlap_char_pos = 0
    cur_pos = 0
    prev_block_obj = editor.srt_blocks[prev_block_idx]
    prev_has_no_base_text = False

    for b in turn_blocks:
        if b.get('overlap_info'):
            # When reconstructing the turn text for a block that itself has
            # overlap_info, include the overlap text in the reconstruction
            # so that chain overlaps (overlaps targeting this block) can
            # be positioned correctly.
            ot = b['overlap_info'].get('overlap_text', '')
            ot_clean = ot
            if ot_clean.startswith('└'):
                ot_clean = ot_clean[1:]  # strip TiQ marker
            elif ot_clean.startswith('[') and ot_clean.endswith(']'):
                ot_clean = ot_clean[1:-1]  # strip GAT2 brackets
            raw = b['overlap_info'].get('text_before', '')
            if raw and ot_clean:
                raw += ' ' + ot_clean
            elif ot_clean:
                raw = ot_clean
            if raw and b['overlap_info'].get('text_after', ''):
                raw += ' ' + b['overlap_info']['text_after']
            elif b['overlap_info'].get('text_after', ''):
                raw = b['overlap_info']['text_after']
        else:
            raw = replace_indent_placeholders(b['raw_text'], editor.INDENT_PLACEHOLDER, editor.cjk_mode, for_export=True)
        
        if not raw.strip():
            if b is prev_block_obj:
                prev_has_no_base_text = True
            continue
        
        if turn_parts:
            cur_pos += len(delimiter)
        
        if b is prev_block_obj:
            # The indent is measured from the start of the raw_text in the viewer.
            # If the target block has its own overlap, subtract its indent
            # so the chain overlap aligns with the overlap text content,
            # not with the leading placeholders.
            prev_self_info = b.get('overlap_info')
            if prev_self_info and prev_self_info.get('indent', 0) > 0:
                # Subtract the target block's own indent (leading placeholders)
                # plus 1 for the └ or [ marker, since the reconstructed turn
                # text includes the overlap_text without the marker prefix.
                offset = prev_self_info['indent']
                ot = prev_self_info.get('overlap_text', '')
                if ot and (ot.startswith('└') or ot.startswith('[')):
                    offset += 1
                overlap_char_pos = cur_pos + max(0, overlap_info['indent'] - offset)
            else:
                overlap_char_pos = cur_pos + overlap_info['indent']
        
        turn_parts.append(raw)
        cur_pos += len(raw)
    
    # If prev_block has no base text (100% overlap block), its overlap text
    # maps position n in raw_text to column n in the export overlap line.
    # So overlap_info.indent gives the correct column directly.
    if prev_has_no_base_text:
        return max(0, overlap_info.get('indent', 0))
    
    turn_text = delimiter.join(turn_parts)
    
    # If pre_wrapped_lines is available, use it directly instead of re-wrapping    # If pre_wrapped_lines is available, use it directly instead of re-wrapping
    if pre_wrapped_lines is not None:
        for line_str, cum_start in pre_wrapped_lines:
            line_end = cum_start + len(line_str)
            if overlap_char_pos < line_end:
                return overlap_char_pos - cum_start
            # Handle boundary: overlap at exact end of line → column 0 on next line
            if overlap_char_pos == line_end:
                return 0
        return 0  # fallback
    
    col = _find_overlap_column(turn_text, overlap_char_pos, max_width, editor, cjk_mode, delimiter)
    return col


def _infer_overlap_info_from_raw_text(block, indent_placeholder):
    """Try to reconstruct virtual overlap_info from old-format inline markers.
    
    Old GAT2 format: "text_before␣␣␣[selected]text_after"
    Old TiQ format:  "text_before␣␣␣└selected_text"
    
    Returns a dict with keys matching overlap_info, or None if not detectable.
    """
    import re as _re
    raw = block.get('raw_text', '')
    if not raw:
        return None
    if indent_placeholder not in raw:
        return None

    ph_esc = _re.escape(indent_placeholder)

    # Try TiQ pattern: ␣␣␣└...
    tiq_match = _re.search(ph_esc + r'+(└)', raw)
    if tiq_match:
        ph_start = tiq_match.start()
        indent = raw[ph_start:tiq_match.start(1)].count(indent_placeholder)
        text_before = raw[:ph_start].strip()
        overlap_text = raw[tiq_match.start(1):]
        return {
            'indent': indent,
            'overlap_text': overlap_text,
            'prev_block_idx': None,
            'convention': 'tiq',
            'text_before': text_before,
            'text_after': ''
        }

    # Try GAT2 pattern: ␣␣␣[...]
    gat2_match = _re.search(ph_esc + r'+(\[)', raw)
    if gat2_match:
        ph_start = gat2_match.start()
        bracket_start = gat2_match.start(1)
        indent = raw[ph_start:bracket_start].count(indent_placeholder)
        text_before = raw[:ph_start].strip()
        close_bracket = raw.find(']', bracket_start)
        if close_bracket == -1:
            return None
        overlap_text = raw[bracket_start:close_bracket + 1]
        text_after = raw[close_bracket + 1:].strip()
        return {
            'indent': indent,
            'overlap_text': overlap_text,
            'prev_block_idx': None,
            'convention': 'gat2',
            'text_before': text_before,
            'text_after': text_after
        }

    return None


def _wrap_with_indent(line, max_width, indent):
    """Wrap a line that has a fixed indent prefix, keeping indent on continuation lines.
    
    The first output line preserves the original prefix (e.g. including speaker label).
    If the full prefix would overflow, it's clipped enough to show at least 4 content chars.
    Continuation lines use space-based indentation, also capped to leave room for content.
    """
    if len(line) <= max_width:
        return [line]
    
    min_content = 4
    
    # First line: cap the prefix so at least min_content chars of text fit
    first_prefix_len = min(indent, max_width - min_content)
    first_prefix = line[:first_prefix_len]
    first_step = max_width - len(first_prefix)
    if first_step < min_content:
        first_step = min_content
    
    result = []
    content = line[indent:]
    first_chunk = content[:first_step]
    if first_chunk:
        result.append(first_prefix + first_chunk)
    
    # Continuation lines: capped indent, all spaces (no speaker labels)
    remaining = line[len(first_prefix) + len(first_chunk):]
    cont_indent = min(indent, max_width - min_content)
    cont_prefix = " " * cont_indent
    cont_step = max_width - len(cont_prefix)
    
    for i in range(0, len(remaining), cont_step):
        chunk = remaining[i:i + cont_step]
        if chunk:
            result.append(cont_prefix + chunk)
    
    return result if result else [line]
    if first_chunk:
        result.append(line[:indent] + first_chunk)
    
    # Continuation lines
    pos = indent + len(first_chunk)
    rest = line[pos:]
    for i in range(0, len(rest), cont_step):
        chunk = rest[i:i + cont_step]
        if chunk:
            result.append(cont_indent_str + chunk)
    
    return result if result else [line]

    
    return result


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

