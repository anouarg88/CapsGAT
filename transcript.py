"""Transcript data model for CapsQual.

Defines the core Transcript dataclass and shared constants used across
parsers, generators, and the GUI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Shared constants ──────────────────────────────────────────────

INDENT_PLACEHOLDER = '␣'  # U+2423 OPEN BOX — visible in viewer

# Regex for pause symbols (atomic tokens)
PAUSE_PATTERN = re.compile(
    r'\(\.\)|\(-+\)|\(\d+(?:\.\d+)?\)|°h+|h+°|@\(\.\)@|@\(\d+s\)@|//|<<.*?>>|\[.*?\]|\(\(.*?\)\)|└'
)


# ── Core data model ───────────────────────────────────────────────

@dataclass
class Transcript:
    """The central data model for a CapsQual transcript.

    Holds all data needed by generators (formatting/export) and the GUI.
    Replaces the ad-hoc ``editor.srt_blocks`` + ``editor.speakers`` +
    ``editor.cjk_mode`` + ``editor.file_has_timestamps`` attributes.
    """

    blocks: list[dict] = field(default_factory=list)
    """List of segment dicts. Each dict has at least:

    - ``index``: int
    - ``start_time`` / ``end_time``: str (``HH:MM:SS,mmm``)
    - ``text`` / ``raw_text``: str
    - ``speaker``: int | None  (index into ``speakers``)
    - ``is_turn_start``: bool
    - ``is_pause`` / ``is_comment`` / ``is_empty``: bool (optional)
    - ``overlap_info``: dict | None (optional)
    """

    speakers: list[str] = field(default_factory=lambda: ["A", "B", "C", "D"])
    """List of speaker names (default A, B, C, D)."""

    cjk_mode: bool = False
    """When True, use CJK-aware wrapping (no spaces between tokens)."""

    file_has_timestamps: bool = True
    """Whether the source file contained timestamp information."""

    # ── convenience helpers ────────────────────────────────────

    @property
    def num_speakers(self) -> int:
        return len(self.speakers)

    def speaker_name(self, speaker_idx: Optional[int]) -> str:
        """Return the display name for a speaker index, or empty string."""
        if speaker_idx is not None and 0 <= speaker_idx < len(self.speakers):
            return self.speakers[speaker_idx]
        return ""

    def __getitem__(self, index: int) -> dict:
        """Access blocks by index directly."""
        return self.blocks[index]

    def __len__(self) -> int:
        return len(self.blocks)
