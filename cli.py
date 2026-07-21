"""Command-line interface for CapsQual.

Usage:

    capsqual input.srt -f gat2 -o output.txt       # Convert (default action)
    capsqual -g                                     # Launch GUI
    capsqual input.srt --speaker="$:"               # Convert with auto-diarization
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from transcript import Transcript
from parsers import parse_srt, parse_text, parse_tsv, parse_json


# ── Speaker-pattern handling ──────────────────────────────────────

def _compile_speaker_pattern(pattern_spec: str) -> tuple[re.Pattern, str]:
    """Compile a ``--speaker`` pattern into a (regex, speaker_key) pair.

    Supported patterns:

    ==========  =========================================
    Pattern     Meaning
    ==========  =========================================
    ``$:``      Speaker name before colon (``Alice: text``)
    ``[$]``     Speaker name in square brackets (``[Alice] text``)
    ``{$}``     Speaker name in curly braces (``{Alice} text``)
    ==========  =========================================

    The ``$`` wildcard captures the speaker name group.
    """
    if pattern_spec == "$:":
        return re.compile(r'^([A-Za-z0-9_ ]+?):\s*(.*)'), "$:"
    elif pattern_spec == "[$]":
        return re.compile(r'^\[([^\]]+)\]\s*(.*)'), "[$]"
    elif pattern_spec == "{$}":
        return re.compile(r'^\{([^}]+)\}\s*(.*)'), "{$}"
    else:
        # Custom regex: user supplies the full pattern with a named group
        return re.compile(pattern_spec), "custom"


def _apply_speaker_pattern(blocks: list[dict],
                            pattern: re.Pattern,
                            pattern_kind: str) -> list[dict]:
    """Apply a speaker-detection pattern to all unassigned blocks.

    Modifies blocks in place and returns them for convenience.
    """
    speaker_names: list[str] = []
    speaker_map: dict[str, int] = {}

    for block in blocks:
        if block["speaker"] is not None:
            continue  # already assigned
        text = block.get("raw_text") or block.get("text", "")
        m = pattern.match(text)
        if not m:
            continue
        name = m.group(1).strip()
        rest = m.group(2).strip()

        # Register or look up speaker
        if name not in speaker_map:
            speaker_map[name] = len(speaker_names)
            speaker_names.append(name)

        block["speaker"] = speaker_map[name]
        block["raw_text"] = rest
        block["text"] = rest

    return blocks


# ── Argument parser ───────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capsqual",
        description="CapsQual — subtitle-to-transcript formatting workstation",
        epilog=(
            "Examples:\n"
            "  capsqual transcript.srt                         Convert to GAT2 text\n"
            "  capsqual transcript.srt -f tiq --speaker=\"$:\"  TiQ with auto-diarization\n"
            "  capsqual transcript.srt -f srt -o out.srt       Re-export as SRT\n"
            "  capsqual -g                                     Launch the GUI\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── GUI flag ──────────────────────────────────────────────
    parser.add_argument("-g", "--gui", action="store_true",
                        help="Launch the CapsQual GUI")

    # ── Input file (positional, optional) ──────────────────────
    parser.add_argument("input", nargs="?",
                        help="Input file (.srt, .txt, .tsv, .json)")

    # ── Output options ─────────────────────────────────────────
    parser.add_argument("-o", "--output",
                        help="Output file path (default: input name + .txt)")
    parser.add_argument("-f", "--format", default="gat2",
                        choices=["gat2", "tiq", "dresing_pehl", "srt"],
                        help="Transcript convention (default: gat2)")

    # Timestamps
    parser.add_argument("-t", "--timestamps", default=True,
                        action=argparse.BooleanOptionalAction,
                        help="Include timestamps (default: True)")
    parser.add_argument("--timestamp-style", default="curly",
                        choices=["curly", "hash", "bracket", "custom"],
                        help="Timestamp style (default: curly)")
    parser.add_argument("--custom-pattern",
                        help="Custom timestamp pattern (e.g. '{HH:mm:ss}')")

    # Diarization
    parser.add_argument("-d", "--diarization", default=True,
                        action=argparse.BooleanOptionalAction,
                        help="Include speaker diarization (default: True)")
    parser.add_argument("-s", "--speaker",
                        help=(
                            "Speaker detection pattern. "
                            'Use "$:" (Alice:), "[$]" ([Alice]), or "{$}" ({Alice}). '
                            "When set, unmapped speakers are auto-assigned."
                        ))
    parser.add_argument("--include-unassigned", action="store_true",
                        help="Include blocks without speaker assignment (default: skip)")

    # Wrapping
    parser.add_argument("-w", "--wrap", type=int, default=0,
                        help="Wrap output to N characters (0 = no wrap)")
    parser.add_argument("--character-wrap", action="store_true",
                        help="Character-level wrapping (for CJK)")

    # Layout
    parser.add_argument("--blank-lines", action="store_true",
                        help="Add blank lines between speaker turns")
    parser.add_argument("--concatenate-turns", action="store_true",
                        help="Concatenate consecutive same-speaker blocks into turns")

    # Delimiter
    parser.add_argument("--delimiter", default="space",
                        choices=["space", "default", "custom"],
                        help="Delimiter between segments (default: space)")
    parser.add_argument("--custom-delimiter",
                        help="Custom delimiter text")

    # SRT-specific
    parser.add_argument("--unassigned", default="skip",
                        choices=["skip", "no_label", "unknown"],
                        help="How to handle unassigned segments in SRT output")

    return parser


# ── Conversion logic ──────────────────────────────────────────────

def run_convert(args: argparse.Namespace) -> int:
    """Convert a subtitle file to a formatted transcript. Returns exit code."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    # ── 1. Parse input ─────────────────────────────────────────
    ext = input_path.suffix.lower()
    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read()

    try:
        if ext == ".srt":
            blocks = parse_srt(raw)
        elif ext == ".txt":
            blocks = parse_text(raw)
        elif ext == ".tsv":
            blocks = parse_tsv(raw)
        elif ext == ".json":
            import json as _json
            data = _json.loads(raw)
            blocks = parse_json(data, import_option="one_block")
        else:
            print(f"Error: unsupported file extension: {ext}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error parsing {input_path}: {e}", file=sys.stderr)
        return 1

    # ── 2. Apply speaker detection if requested ─────────────────
    if args.speaker:
        pattern, kind = _compile_speaker_pattern(args.speaker)
        _apply_speaker_pattern(blocks, pattern, kind)

    # ── 3. Build Transcript ─────────────────────────────────────
    has_ts = any(
        b.get("start_time") for b in blocks if b.get("start_time")
    )
    transcript = Transcript(
        blocks=blocks,
        speakers=["A", "B", "C", "D"],
        cjk_mode=False,
        file_has_timestamps=has_ts,
    )

    # ── Handle unassigned blocks (run BEFORE generation) ─────
    if args.include_unassigned and args.speaker is None:
        for block in blocks:
            if block["speaker"] is None and not block.get("is_pause") and not block.get("is_comment"):
                block["speaker"] = 0

    # ── 4. Determine output path ────────────────────────────────
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = input_path.with_suffix(".txt")

    # ── 5. Generate transcript ──────────────────────────────────
    from generators import (
        generate_srt_text,
        generate_transcript_text,
    )

    wrap = args.wrap if args.wrap and args.wrap > 0 else False
    wrap_length = args.wrap if args.wrap and args.wrap > 0 else 80

    if args.format == "srt":
        text = generate_srt_text(
            transcript,
            include_diarization=args.diarization,
            unassigned_handling=args.unassigned,
        )
    else:
        text = generate_transcript_text(
            transcript,
            include_timestamps=args.timestamps,
            timestamp_style=args.timestamp_style,
            custom_pattern=args.custom_pattern,
            convention=args.format,
            include_diarization=args.diarization,
            wrap_enabled=bool(wrap),
            wrap_length=wrap_length,
            character_wrap=args.character_wrap,
            add_blank_line=args.blank_lines,
            concatenate_turns=args.concatenate_turns,
            delimiter_choice=args.delimiter,
            custom_delimiter=args.custom_delimiter or "",
        )

    # ── 6. Write output ─────────────────────────────────────────
    from export import (
        build_html_content,
        write_html_file,
        write_txt_file,
        write_srt_file,
        write_docx_file,
    )

    out_ext = out_path.suffix.lower()

    try:
        if out_ext == ".html":
            html = build_html_content(
                text,
                {"convention": args.format, "include_title": False,
                 "include_memo": False, "include_audio": False},
                {"name": input_path.stem},
            )
            write_html_file(html, str(out_path))
        elif out_ext == ".docx":
            success = write_docx_file(
                text,
                {"convention": args.format, "include_title": True,
                 "include_memo": False, "include_audio": False},
                {"name": input_path.stem},
                None,
                str(out_path),
            )
            if not success:
                print("Warning: python-docx not available; falling back to .txt",
                      file=sys.stderr)
                out_path = out_path.with_suffix(".txt")
                write_txt_file(text, str(out_path))
        elif out_ext == ".srt":
            write_srt_file(text, str(out_path))
        else:
            write_txt_file(text, str(out_path))
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {out_path}")
    return 0


# ── GUI launcher ──────────────────────────────────────────────────

def run_gui() -> int:
    """Launch the CapsQual graphical interface. Returns exit code."""
    try:
        from main import main as gui_main
        gui_main()
        return 0
    except Exception as e:
        print(f"Error launching GUI: {e}", file=sys.stderr)
        print("(The GUI requires PyQt5; try 'pip install PyQt5')", file=sys.stderr)
        return 1


# ── Entry point ───────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ── GUI mode ───────────────────────────────────────────────
    if args.gui:
        return run_gui()

    # ── Convert mode (default when input file given) ────────────
    if args.input:
        return run_convert(args)

    # ── Nothing to do ──────────────────────────────────────────
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
