# CapsQual Codebase Overview

> _2026-07-23_

---

## 🏗️ Architecture at a Glance

```
main.py                  ← Entry point (bootstrap + splash)
   │
   ├── cli.py            ← CLI entry point (argparse, convert, GUI launcher)
   │
   ├── editor.py         ← Main window & UI controller (SRTEditor)
   ├── dialogs.py        ← Dialog windows
   │
   ├── parsers.py        ← Stateless subtitle/transcript parsers
   ├── transcript.py     ← Transcript dataclass (core data model)
   ├── generators.py     ← Transcript text generation (GAT2/TiQ/Dresing&Pehl)
   ├── export.py         ← File writing (HTML/DOCX/TXT/SRT)
   │
   ├── audio_players.py  ← Audio playback (VLC + PyAudio)
   ├── widgets.py        ← Custom UI widgets
   ├── highlighting.py   ← Syntax highlighting
   ├── utils.py          ← Shared utilities
   │
   ├── tests/            ← Test suite
   └── README.md         ← User-facing documentation
```

---

## 📁 Core Modules

### 🟢 `main.py` — Entry Point (45 lines)

- Creates `QApplication`, shows splash screen
- Instantiates `SRTEditor` (from `editor.py`), calls `preload_modules()`
- Hands control to Qt event loop

**Key imports:**
- `editor.SRTEditor`
- `utils.resource_path`

---

### 🟢 `cli.py` — Command-Line Interface (320 lines)

> _New module — extracted to enable headless conversion._

| Function | Purpose |
|----------|---------|
| `build_parser()` | Build argparse with input, output, format, diarization, layout options |
| `run_convert()` | Parse input → apply speaker detection → build Transcript → generate → write output |
| `run_gui()` | Launch the CapsQual GUI |
| `main()` | Entry point: dispatches to GUI mode (`-g`) or convert mode |

**CLI examples:**
```bash
capsqual transcript.srt                     # Convert to GAT2 text
capsqual input.srt -f tiq --speaker="$:"    # TiQ with auto-diarization
capsqual input.srt -o transcript.html       # Export as HTML
capsqual -g                                 # Launch GUI
```

**Dependencies:** `transcript.py`, `parsers.py`, `generators.py`, `export.py`

---

### 🟢 `editor.py` — Main Editor Window (4015 lines)

This is the main window and does almost everything:

| Area | Lines | What it does |
|------|-------|-------------|
| **`__init__`** | ~140 | Sets up UI, loads project, initializes audio |
| **File I/O** | ~200 | Load/save `.capsqual` project files, import SRT/JSON/TSV/TXT |
| **Segment editing** | ~300 | Split, merge, reassign speakers, edit timestamps |
| **Symbols/annotations** | ~250 | `apply_symbol()`, insert pauses/comments/overlaps |
| **Audio sync** | ~200 | Seek to block on audio click, update block on audio position |
| **Export generation** | ~100 | Calls `generators.py` functions, then `final_export()` |
| **`final_export()`** | ~50 | Opens save dialog, delegates to `export.py` |
| **UI helpers** | ~200 | Context menus, keyboard shortcuts, drag-drop |

**Known risk:** ~37% of the codebase — god class with UI, I/O, audio, export, search, and settings all in one class.

---

### 🟢 `dialogs.py` — Dialog Windows (2694 lines)

All popup dialogs live here:

| Class | Purpose |
|-------|---------|
| `TextSelectionDialog` | Select text from a block with arrow keys |
| `BlockSplitDialog` | Position a split point in a block |
| `EditTimestampsDialog` | Edit start/end times with HH/mm/ss/SSS spinboxes |
| `InsertPausesDialog` | Configure pause insertion settings |
| `AddCustomSymbolDialog` | Add user-defined symbols (simple, wrapper, comment) |
| `ExportDialog` | Preview and configure export (HTML/TXT/DOCX/SRT) |
| `PlacementDialog` | Symbol placement indicator |
| `SymbolCategory` | Helper for symbol categories |
| *(many more for JSON import, credits, etc.)* | |

**Dark mode:** Dialogs now detect `_is_dark_parent()` at init and use theme-responsive HTML colors in `update_display()` methods.

---

### 🟢 `parsers.py` — Subtitle Parsers (388 lines)

> _New module — stateless parsing functions extracted from `editor.py`._

| Function | Purpose |
|----------|---------|
| `parse_srt(text)` | Parse SRT → list of block dicts |
| `parse_vtt(text)` | Parse WebVTT → list of block dicts |
| `parse_json(data, import_option)` | Parse JSON → list of block dicts |
| `parse_tsv(text)` | Parse TSV → list of block dicts |
| `parse_text(text)` | Parse plain text → list of block dicts |

All functions are pure Python with **no Qt imports** — usable from CLI.

---

### 🟢 `transcript.py` — Transcript Data Model (72 lines)

> _New module — core data model extracted from `editor.py`._

```python
@dataclass
class Transcript:
    blocks: list[dict]           # Segment data (text, speaker, timestamps, etc.)
    speakers: list[str]          # Display names for each speaker index
    cjk_mode: bool               # CJK character-wrapping mode
    file_has_timestamps: bool    # Whether blocks have timing info
```

The `Transcript` dataclass is the canonical data model passed between `parsers.py` → `generators.py` → `export.py`.

---

### 🟢 `generators.py` — Transcript Generation (1737 lines)

Contains all logic for *generating* formatted transcript text.

| Function | Purpose |
|----------|---------|
| `time_to_seconds()` / `time_to_ms()` | Convert "HH:MM:SS,mmm" to seconds/milliseconds |
| `format_timestamp()` | Format seconds into timestamp strings |
| `get_timestamp_width()` | Get character width of a timestamp style |
| `format_srt_time()` | Normalize time string to SRT format |
| `strip_markup()` | Remove `#@B`, `#@I`, `#@U` formatting markers |
| `escape_html()` | Escape `&`, `<`, `>`, `"`, `'` for HTML |
| `convert_markup_to_html()` | Convert markers to `<b>`/`<i>`/`<u>` |
| `generate_gat2_text()` | Generate GAT2-convention transcript |
| `generate_dresing_pehl_text()` | Generate Dresing & Pehl-convention transcript |
| `generate_tiq_text()` | Generate TiQ-convention transcript |
| `generate_srt_text()` | Generate SRT subtitle file content |
| `generate_transcript_text()` | Router → delegates to convention-specific generator |
| `_wrap_text()` | Word-wrap text to a max width |
| `_wrap_with_indent()` | Wrap preserving a fixed indent |

**Conventions supported:**
- **GAT2** — `{00:00:00}` timestamps, `[overlap]`, line-numbered, speaker-labeled
- **TiQ** — `#00:00:00-0#` timestamps, `└overlap`, line-numbered, vertical bars
- **Dresing & Pehl** — `#00:00:00-0#` timestamps or `{00:00:00}`, minimal formatting

---

### 🟢 `export.py` — File Writing (257 lines)

Consolidates all file I/O. Pure Python (no Qt imports).

| Function | Purpose |
|----------|---------|
| `build_html_content()` | Builds a complete HTML document |
| `write_html_file()` | Writes HTML to disk |
| `write_srt_file()` | Writes SRT to disk |
| `write_txt_file()` | Strips markup and writes plain text |
| `write_docx_file()` | Builds and saves DOCX using `python-docx` |
| `add_formatted_paragraph()` | Adds a DOCX paragraph with bold/italic/underline support |

**Dependency:** `generators.py` (for `escape_html`, `convert_markup_to_html`, `strip_markup`)

---

## 🔧 Supporting Modules

### 🟠 `audio_players.py` — Audio Playback (424 lines)

| Class | Purpose |
|-------|---------|
| `SimpleAudioPlayer(QThread)` | Fallback player using PyAudio/soundfile (no speed control) |
| `VLCPlayer` | VLC-based player with speed control (0.5x–2.0x) |
| `has_pyaudio()` | Detect if PyAudio is available |

Both implement signals: `playback_started`, `playback_stopped`, `position_changed`

---

### 🟠 `widgets.py` — Custom Widgets (629 lines)

| Class | Purpose |
|-------|---------|
| `WaveformViewer(QWidget)` | Audio waveform visualization with zoom controls, draggable segment handles, playhead cursor, dark/light theme support |
| `SpeedKnob(QWidget)` | A circular rotary knob for playback speed (0.5x–2.0x) with mouse drag/wheel support |

> ⚠️ **Scope expansion:** Originally 136 lines (SpeedKnob only), now 629 lines with the addition of `WaveformViewer` — a 4.6× growth from the original architecture doc.

---

### 🟠 `highlighting.py` — Syntax Highlighting (51 lines)

| Class | Purpose |
|-------|---------|
| `FormattingMarkerHighlighter(QSyntaxHighlighter)` | Highlights `#@B`/`#@I`/`#@U` markers and applies bold/italic/underline to enclosed text in QTextEdit |

---

### 🟠 `utils.py` — Shared Utilities (22 lines)

- `logger` — Module-level logger
- `resource_path()` — Resolves paths for PyInstaller bundles (`sys._MEIPASS`)

---

## 🧪 Test Suite

| File | Lines | Tests | What it tests |
|------|-------|-------|--------------|
| `tests/test_export.py` | 1035 | 39 | GAT2/TiQ/Dresing&Pehl/SRT generation, overlap handling, blank lines, vertical bars |
| `tests/test_parsing.py` | 136 | 6 | SRT/JSON/TSV/TXT file parsing |
| `tests/test_cli.py` | 388 | ~25 | CLI workflow, speaker detection, format conversions, error handling |
| `tests/test_ui.py` | 270 | 7 | Timestamp formatting, time conversion, misc UI utilities |
| **Total** | **1829** | **~77** | |

Run with: `python -m pytest tests/ -v`

---

## 📦 Dependencies (`requirements.txt`)

| Package | Purpose |
|---------|---------|
| `PyQt5` | GUI framework |
| `python-docx` | DOCX export |
| `pyaudio` | Fallback audio playback |
| `soundfile` | Audio file reading for fallback player |
| `numpy` | Audio data processing |
| `python-vlc` | VLC-based audio playback with speed control |

---

## 🔄 Data Flow

```
                         ┌──────────────────┐
                         │   SRT / VTT /    │
                         │  JSON / TSV / TXT │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
              parsers.py                     editor.py
         (parse_srt/parse_vtt/          (GUI import handlers)
          parse_json/parse_tsv/              │
          parse_text)                        │
                    │                        │
                    └──────────┬─────────────┘
                               ▼
                        transcript.py
                     (Transcript dataclass)
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
      cli.py              editor.py            dialogs.py
  (run_convert())     (editing / symbols)    (ExportDialog)
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
                        generators.py
                   (generate_*_text() functions)
                               │
                               ▼
                          text (str)
                               │
                               ▼
                         export.py
                 (build_html/write_docx/
                  write_txt/write_srt)
                               │
                               ▼
                    HTML / DOCX / TXT / SRT
```

---

## 🎨 Export Format Details

### HTML Output Structure
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: 'Courier New', monospace; font-size: 10pt; }
    p { margin: 0; padding: 0; }
  </style>
</head>
<body>
  <h1>Project Name</h1>
  <p>{00:00:00}&nbsp;&nbsp;&nbsp;01&nbsp;&nbsp;A:&nbsp;&nbsp;Hello</p>
  <br>                                           ← blank lines
  <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;03&nbsp;&nbsp;nein&nbsp;(.)</p>
</body>
</html>
```

**Key features for QDA compatibility:**
- `<p>` tags (not `<br>` — some software handles paragraphs better)
- `&nbsp;` entities instead of spaces (some software strips leading spaces upon import)
- No `white-space: pre-wrap` CSS (redundant with `&nbsp;`)
- Blank lines as `<br>` (visible even with `p { margin:0; }`)

---

## ⚠️ Cross-Cutting Risks

| Risk | Module | Impact |
|------|--------|--------|
| **God class** | `editor.py` (4015L, ~37%) | UI, I/O, audio, export, search, settings all in one class — any change risks ripple effects |
| **Widget scope drift** | `widgets.py` (629L vs documented 136L) | WaveformViewer adds audio viz but doc was never updated — 4.6× growth |
| **Backup file in source** | `editor_bak_7-8.py` (4259L) | Orphan backup sitting in source dir could confuse tools |
| **Duplicated time conversion** | `editor.py`, `generators.py`, `parsers.py` | `ms_to_time()` exists in 3 places — should be deduplicated |
| **Auto-pause duplication** | `editor.py` | 13+ methods duplicate the pause-audio → dialog → resume pattern |
| **Dialog sprawl** | `dialogs.py` (2694L) | 15+ dialog classes in one file — could be decomposed |

---

## 🔍 Finding Your Way Around

| I want to... | Look in... |
|-------------|-----------|
| Use CapsQual from the command line | `cli.py` — `capsqual input.srt -f gat2 -o output.txt` |
| Change how transcripts are formatted | `generators.py` — e.g., `generate_gat2_text()` |
| Change HTML export appearance | `export.py` — `build_html_content()` |
| Add a new dialog | `dialogs.py` — create a new `QDialog` subclass |
| Change the main editor UI | `editor.py` — `SRTEditor` class |
| Edit audio playback | `audio_players.py` — `SimpleAudioPlayer` or `VLCPlayer` |
| Add/modify tests | `tests/test_export.py`, `test_cli.py`, `test_parsing.py`, or `test_ui.py` |
| Change keyboard shortcuts | `editor.py` — `init_shortcuts()` near `__init__` |
| Modify symbol/annotation logic | `editor.py` — `apply_symbol()` |
| Change export file-writing | `export.py` — `write_html_file()`, `write_docx_file()`, etc. |
| Parse a subtitle format | `parsers.py` — `parse_srt()`, `parse_json()`, etc. |
| Understand the data model | `transcript.py` — `Transcript` dataclass |
