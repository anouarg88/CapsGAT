# CapsQual Codebase Overview

> _2026-07-09_

---

## 🏗️ Architecture at a Glance

```
main.py                  ← Entry point
   │
   ├── editor.py         ← Main window & UI controller
   ├── dialogs.py        ← Dialog windows
   │
   ├── generators.py     ← Transcript text generation
   ├── export.py         ← File writing (HTML/DOCX/TXT/SRT)
   │
   ├── audio_players.py  ← Audio playback
   ├── widgets.py        ← Custom UI widgets
   ├── highlighting.py   ← Syntax highlighting
   ├── utils.py          ← Shared utilities
   │
   ├── tests/            ← Test suite
   ├── README.md         ← User-facing documentation
   └── build.yml         ← CI/CD for Windows/macOS/Linux
```

---

## 📁 Core Modules

### 🟢 `main.py` — Entry Point

- Creates `QApplication`, shows splash screen
- Instantiates `SRTEditor` (from `editor.py`), calls `preload_modules()`
- Hands control to Qt event loop

**Key imports:**
- `editor.SRTEditor`
- `utils.resource_path`

---

### 🟢 `editor.py` — Main Editor Window

This is the actual main window and does almost everything:

| Area | Lines | What it does |
|------|-------|-------------|
| **`__init__`** | ~140 | Sets up UI, loads project, initializes audio |
| **File I/O** | ~200 | Load/save `.capsqual` project files, import SRT/JSON/TSV/TXT |
| **Parsers** | ~400 | `parse_srt()`, `parse_json()`, `parse_tsv()`, `parse_text()` — converts subtitle files into internal `srt_blocks` format |
| **Segment editing** | ~300 | Split, merge, reassign speakers, edit timestamps |
| **Symbols/annotations** | ~250 | `apply_symbol()`, insert pauses/comments/overlaps |
| **Audio sync** | ~200 | Seek to block on audio click, update block on audio position |
| **Export generation** | ~100 | Calls `generators.py` functions to generate transcript text, then calls `final_export()` |
| **`final_export()`** | ~50 | Opens save dialog, delegates to `export.py` for file writing |
| **UI helpers** | ~200 | Context menus, keyboard shortcuts, drag-drop |

**Internal data structure (`self.srt_blocks`):**  
A list of dicts, each representing one transcript segment:
```python
{
    'index': int,
    'text': str,           # Display text
    'raw_text': str,        # Original text with formatting markers
    'speaker': int | None,  # Index into self.speakers
    'start_time': str,      # "HH:MM:SS,mmm"
    'end_time': str,
    'is_turn_start': bool,
    'is_pause': bool,
    'is_comment': bool,
    'overlap_info': dict | None,  # Overlap positioning data
}
```

---

### 🟢 `dialogs.py` — Dialog Windows (2440 lines)

All popup dialogs live here:

| Class | Purpose |
|-------|---------|
| `TextSelectionDialog` | Select text from a block with arrow keys |
| `BlockSplitDialog` | Position a split point in a block |
| `EditTimestampsDialog` | Edit start/end times with HH/mm/ss/SSS spinboxes |
| `InsertPausesDialog` | Configure pause insertion settings |
| `AddCustomSymbolDialog` | Add user-defined symbols (simple, wrapper, comment) |
| `ExportDialog` | Preview and configure export (HTML/TXT/DOCX/SRT) |
| `SymbolCategory` | Helper for symbol categories |
| *(many more for JSON import, credits, etc.)* | |

**Key function:** `ExportDialog.update_preview()` generates the HTML preview using `export.build_html_content()`.

---

### 🟢 `generators.py` — Transcript Generation (1850 lines)

Contains all logic for *generating* formatted transcript text.

| Function | Purpose |
|----------|---------|
| `time_to_seconds()` / `time_to_ms()` | Convert "HH:MM:SS,mmm" to seconds/milliseconds |
| `format_timestamp()` | Format seconds into timestamp strings (`{curly}`, `#hash#`, `[bracket]`, custom) |
| `get_timestamp_width()` | Get character width of a timestamp style |
| `format_srt_time()` | Normalize time string to SRT format |
| `strip_markup()` | Remove `#@B`, `#@I`, `#@U` formatting markers |
| `escape_html()` | Escape `&`, `<`, `>`, `"`, `'` for HTML |
| `convert_markup_to_html()` | Convert `#@B`/`#@I`/`#@U` to `<b>`/`<i>`/`<u>` |
| `replace_indent_placeholders()` | Replace indent placeholders with spaces |
| `generate_gat2_text()` | Generate GAT2-convention transcript |
| `generate_dresing_pehl_text()` | Generate Dresing & Pehl-convention transcript |
| `generate_tiq_text()` | Generate TiQ-convention transcript |
| `generate_srt_text()` | Generate SRT subtitle file content |
| `generate_transcript_text()` | Router → delegates to convention-specific generator |
| `estimate_missing_timestamps()` | Interpolate timestamps for blocks without them |
| `_group_into_turns()` | Group consecutive same-speaker blocks |
| `_build_ordered_segments()` | Build ordered segments with turn grouping |
| `_tokenize_with_pauses()` / `_tokenize_cjk_with_pauses()` | Tokenize text for wrapping |
| `_wrap_text()` | Word-wrap text to a max width |
| `_wrap_with_indent()` | Wrap preserving a fixed indent |
| `_find_overlap_column()` | Find wrapping-aware column for overlaps |
| `_compute_overlap_export_indent()` | Compute overlap line indentation |
| `_rebreak_turn_line_for_overlap()` | Re-break a wrapped line to make room for overlap |
| `_infer_overlap_info_from_raw_text()` | Detect old-format overlap markers |
| `_ms_to_time()` | Convert ms → "HH:MM:SS,mmm" |

**Conventions supported:**
- **GAT2** — `{00:00:00}` timestamps, `[overlap]`, line-numbered, speaker-labeled
- **TiQ** — `#00:00:00-0#` timestamps, `└overlap`, line-numbered, vertical bars
- **Dresing & Pehl** — `#00:00:00-0#` timestamps or `{00:00:00}`, minimal formatting

---

### 🟢 `export.py` — File Writing (256 lines)

Consolidates all file I/O. Pure Python (no Qt imports).

| Function | Purpose |
|----------|---------|
| `build_html_content()` | Builds a complete HTML document: `<p>` tags per line, `&nbsp;` for spaces, `<br>` for blank lines, CSS styling |
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

### 🟠 `widgets.py` — Custom Widgets (136 lines)

| Class | Purpose |
|-------|---------|
| `SpeedKnob(QWidget)` | A circular rotary knob for playback speed (0.5x–2.0x) with mouse drag/wheel support |

---

### 🟠 `highlighting.py` — Syntax Highlighting (51 lines)

| Class | Purpose |
|-------|---------|
| `FormattingMarkerHighlighter(QSyntaxHighlighter)` | Highlights `#@B`/`#@I`/`#@U` markers and applies bold/italic/underline to enclosed text in QTextEdit |

---

### 🟠 `utils.py` — Shared Utilities (16 lines)

- `logger` — Module-level logger
- `resource_path()` — Resolves paths for PyInstaller bundles (`sys._MEIPASS`)

---

## 🧪 Test Suite

| File | Tests | What it tests |
|------|-------|--------------|
| `tests/test_export.py` | 39 | GAT2/TiQ/Dresing&Pehl/SRT generation, overlap handling, blank lines, vertical bars |
| `tests/test_parsing.py` | 6 | SRT/JSON/TSV/TXT file parsing |
| `tests/test_ui.py` | 7 | Timestamp formatting, time conversion, misc UI utilities |
| **Total** | **52** | |

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

## 🏗️ Build & CI/CD

- **`build.yml`** — GitHub Actions: builds PyInstaller binaries for Windows, Ubuntu, macOS (Intel + ARM)
- **`pyinstaller.txt`** — Local build commands (single-file and directory mode)
- **`pytest.ini`** — Test configuration (300s timeout, short tracebacks)

---

## 🔄 Data Flow

```
                   Import (SRT/JSON/TSV/TXT)
                            │
                            ▼
                   editor.srt_blocks[]
                   (internal segment list)
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
    editor.py          dialogs.py          generators.py
    (editing UI)       (ExportDialog)      (generate_*_text())
                                                │
                                                ▼
                                           transcript_text (str)
                                                │
                                                ▼
                                           export.py
                                        (build_html, write_docx,
                                         write_txt, write_srt)
                                                │
                                                ▼
                                          📄 HTML/DOCX/TXT/SRT
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

## 🔍 Finding Your Way Around

| I want to... | Look in... |
|-------------|-----------|
| Change how transcripts are formatted | `generators.py` — e.g., `generate_gat2_text()` |
| Change HTML export appearance | `export.py` — `build_html_content()` |
| Add a new dialog | `dialogs.py` — create a new `QDialog` subclass |
| Change the main editor UI | `editor.py` — `SRTEditor` class |
| Edit audio playback | `audio_players.py` — `SimpleAudioPlayer` or `VLCPlayer` |
| Add/modify tests | `tests/test_export.py` or `tests/test_parsing.py` |
| Change keyboard shortcuts | `editor.py` — `init_shortcuts()` near `__init__` |
| Modify symbol/annotation logic | `editor.py` — `apply_symbol()` |
| Change export file-writing | `export.py` — `write_html_file()`, `write_docx_file()`, etc. |
