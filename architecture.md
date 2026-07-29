# CapsQual Codebase Overview

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
   ├── audio_players.py  ← Audio playback (VLC)
   ├── widgets.py        ← Custom UI widgets
   ├── highlighting.py   ← Syntax highlighting
   ├── utils.py          ← Shared utilities
   │
   ├── tests/            ← Test suite
   └── README.md         ← User-facing documentation
```

---

## 📁 Core Modules

### 🟢 `main.py` — Entry Point

- Creates `QApplication`, shows splash screen
- Instantiates `SRTEditor` and initializes the application
- Hands control to Qt event loop

---

### 🟢 `cli.py` — Command-Line Interface

Provides headless conversion and GUI launching:

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

---

### 🟢 `editor.py` — Main Editor Window

The main window and UI controller. Handles:

- **File I/O** — Load/save `.capsqual` project files, import SRT/JSON/TSV/TXT
- **Segment editing** — Split, merge, reassign speakers, edit timestamps
- **Symbols/annotations** — Insert pauses, comments, overlaps
- **Audio sync** — Seek to block on audio click, update block on audio position
- **Export** — Trigger transcript generation and file writing
- **UI helpers** — Context menus, keyboard shortcuts, drag-drop

---

### 🟢 `dialogs.py` — Dialog Windows

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

---

### 🟢 `parsers.py` — Subtitle Parsers

Stateless parsing functions for importing files:

| Function | Purpose |
|----------|---------|
| `parse_srt(text)` | Parse SRT → list of block dicts |
| `parse_vtt(text)` | Parse WebVTT → list of block dicts |
| `parse_json(data, import_option)` | Parse JSON → list of block dicts |
| `parse_tsv(text)` | Parse TSV → list of block dicts |
| `parse_text(text)` | Parse plain text → list of block dicts |

All functions are pure Python with no Qt imports — usable from CLI.

---

### 🟢 `transcript.py` — Transcript Data Model

Core data model passed between parsing, generation, and export:

```python
@dataclass
class Transcript:
    blocks: list[dict]           # Segment data (text, speaker, timestamps, etc.)
    speakers: list[str]          # Display names for each speaker index
    cjk_mode: bool               # CJK character-wrapping mode
    file_has_timestamps: bool    # Whether blocks have timing info
```

---

### 🟢 `generators.py` — Transcript Generation

Contains all logic for generating formatted transcript text.

**Key functions:**
- `generate_gat2_text()` — Generate GAT2-convention transcript
- `generate_tiq_text()` — Generate TiQ-convention transcript
- `generate_dresing_pehl_text()` — Generate Dresing & Pehl-convention transcript
- `generate_srt_text()` — Generate SRT subtitle file content
- `generate_transcript_text()` — Router that delegates to convention-specific generators

**Conventions supported:**
- **GAT2** — `{00:00:00}` timestamps, `[overlap]`, line-numbered, speaker-labeled
- **TiQ** — `#00:00:00-0#` timestamps, `└overlap`, line-numbered, vertical bars
- **Dresing & Pehl** — `#00:00:00-0#` timestamps or `{00:00:00}`, minimal formatting

---

### 🟢 `export.py` — File Writing

Consolidates file I/O for all export formats. Pure Python (no Qt imports).

| Function | Purpose |
|----------|---------|
| `build_html_content()` | Builds a complete HTML document |
| `write_html_file()` | Writes HTML to disk |
| `write_srt_file()` | Writes SRT to disk |
| `write_txt_file()` | Strips markup and writes plain text |
| `write_docx_file()` | Builds and saves DOCX using `python-docx` |
| `add_formatted_paragraph()` | Adds a DOCX paragraph with bold/italic/underline support |

---

## 🔧 Supporting Modules

### 🟠 `audio_players.py` — Audio Playback

| Class | Purpose |
|-------|---------|
| `VlcAudioPlayer(QThread)` | VLC-based player with speed control (0.5x–2.0x) |

Signals: `playback_started`, `playback_paused`, `playback_stopped`, `position_changed`, `end_reached`

---

### 🟠 `widgets.py` — Custom Widgets

| Class | Purpose |
|-------|---------|
| `WaveformViewer(QWidget)` | Audio waveform visualization with zoom controls, draggable segment handles, playhead cursor, dark/light theme support |
| `SpeedKnob(QWidget)` | A circular rotary knob for playback speed (0.5x–2.0x) with mouse drag/wheel support |

---

### 🟠 `highlighting.py` — Syntax Highlighting

| Class | Purpose |
|-------|---------|
| `FormattingMarkerHighlighter(QSyntaxHighlighter)` | Highlights `#@B`/`#@I`/`#@U` markers and applies bold/italic/underline to enclosed text in QTextEdit |

---

### 🟠 `utils.py` — Shared Utilities

- `logger` — Module-level logger
- `resource_path()` — Resolves paths for PyInstaller bundles

---

## 🧪 Test Suite

| File | What it tests |
|------|--------------|
| `tests/test_export.py` | GAT2/TiQ/Dresing&Pehl/SRT generation, overlap handling, blank lines, vertical bars |
| `tests/test_parsing.py` | SRT/JSON/TSV/TXT file parsing |
| `tests/test_cli.py` | CLI workflow, speaker detection, format conversions, error handling |
| `tests/test_ui.py` | Timestamp formatting, time conversion, misc UI utilities |

Run with: `python -m pytest tests/ -v`

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt5` | GUI framework |
| `python-docx` | DOCX export |
| `soundfile` | Audio file reading for waveform viewer |
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
  <br>
  <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;03&nbsp;&nbsp;nein&nbsp;(.)</p>
</body>
</html>
```

**Key features for QDA compatibility:**
- `<p>` tags (not `<br>` — some software handles paragraphs better)
- `&nbsp;` entities instead of spaces (some software strips leading spaces upon import)
- Blank lines as `<br>` tags

---

## 🔍 Finding Your Way Around

| I want to... | Look in... |
|-------------|-----------|
| Use CapsQual from the command line | `cli.py` |
| Change how transcripts are formatted | `generators.py` — e.g., `generate_gat2_text()` |
| Change HTML export appearance | `export.py` — `build_html_content()` |
| Add a new dialog | `dialogs.py` — create a new `QDialog` subclass |
| Change the main editor UI | `editor.py` — `SRTEditor` class |
| Edit audio playback | `audio_players.py` — `VlcAudioPlayer` |
| Add/modify tests | `tests/` directory |
| Change keyboard shortcuts | `editor.py` |
| Modify symbol/annotation logic | `editor.py` |
| Change export file-writing | `export.py` |
| Parse a subtitle format | `parsers.py` |
| Understand the data model | `transcript.py` — `Transcript` dataclass |
