# CapsQual
![GitHub Release](https://img.shields.io/github/v/release/anouarg88/CapsQual?label=Latest%20release)
[![Run CI tests](https://github.com/anouarg88/CapsQual/actions/workflows/tests.yml/badge.svg)](https://github.com/anouarg88/CapsQual/actions/workflows/tests.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21551449.svg)](https://doi.org/10.5281/zenodo.21551449)

CapsQual (formerly CapsGAT) is an open source cross-platform workstation for editing and reformatting subtitle files (.SRT, .VTT, .JSON, .TSV, .TXT) into qualitative interview transcripts based on different conventions such as the minimal version of GAT2 ([Gesprächsanalytisches Transkriptionssystem 2](https://gat-to.uni-jena.de/)), TiQ (Talk in Qualitative Research) and those suggested by Kuckartz and Dresing & Pehl. The GUI enables users to assign speakers to segments quickly using keyboard shortcuts. Audio files can be imported and synced to the transcript. This is meant to reduce window-switching and simplify the formatting process. Playback speed can be adjusted (requires VLC Player to be installed). CapsQual features essential transcript-editing functionality such as segment splitting and merging, customizable symbols, overlapping speech, pauses, comments and more.  


However, it is not meant as a replacement for dedicated manual transcription software (for full-fledged, professional transcription software, check out [EXMARaLDA](https://www.exmaralda.org)), nor as an all-in-one automated transcription worksuite (for AI-powered transcription with automatic diarization check out [noScribe](https://ai4culture.eu/resources/tools/172)), but as a complementary formatting tool to be used with transcription AI models such as Whisper AI or CapsWriter, aimed at those who wish to efficiently tidy up their automatically transcribed interview-data in a user-friendly, intuitive environment. Projects can be loaded or saved. Transcripts can be exported as .HTML, .DOCX, .TXT or .SRT files.

# Installation

## System Requirements

- **Windows**: 7 or later (64‑bit recommended)
- **macOS**: 10.13 (High Sierra) or later (Intel and Apple Silicon supported)
- **Linux**: any modern distribution (e.g., Ubuntu 20.04+)
- **RAM**: 512 MB minimum, 2 GB recommended
- **Disk space**: 150 MB for the application, plus space for your projects

Optional but highly recommended for audio playback speed control:

- **VLC media player** (download from [videolan.org](https://www.videolan.org/))


## Installation guide

_Note: Version 1.6.0 has been used as an example in this installation guide. Please replace "1.6.0" with whichever version you are going to install._

### Windows

1. Download the Windows installer `CapsQual_1.6.0_Setup.exe` or the portable executable: `CapsQual_1.6.0.exe`.
2. If you downloaded the installer, double‑click and follow the on‑screen instructions.
3. If you downloaded the portable version, simply unzip the file in any folder and double‑click `CapsQual_1.6.0.exe` to run. A system warning may show up, since this software does not contain any official certificates. You may ignore this at your own discretion.
4. (Optional) Install [VLC](https://www.videolan.org/) to enable playback speed control and better audio compatibility before running CapsQual.

To run from source:

```cmd
rem 1. Install Python 3.9+ from python.org (check "Add Python to PATH")
rem 2. Clone the repository
git clone https://github.com/anouarg88/CapsQual.git
cd CapsQual
rem 3. Create a virtual environment
python -m venv venv
venv\Scripts\activate
rem 4. Install dependencies
pip install -r requirements.txt
rem 5. Run
python main.py
```

### macOS

Two versions are provided:

- `CapsQual-macOS-Intel` for Intel‑based Macs (2019 and earlier)
- `CapsQual-macOS-AppleSilicon` for Macs with Apple Silicon (M1, M2, M3)

1. Download the appropriate `.zip` file.
2. Open the downloaded file and drag `CapsQual_1.6.0.app` to your `Applications` folder.
3. The first time you run the app, macOS may warn you that it is from an unidentified developer.  
   To bypass this, right‑click (or Ctrl‑click) the app and select **Open**, then click **Open** again.
4. (Optional) Install [VLC](https://www.videolan.org/) to enable playback speed control before running CapsQual.

To run from source:

```bash
# 1. Install Python 3.9+ (via Homebrew)
brew install python
# 2. Clone the repository
git clone https://github.com/anouarg88/CapsQual.git
cd CapsQual
# 3. Create a virtual environment
python3 -m venv venv
source venv/bin/activate
# 4. Install dependencies
pip install -r requirements.txt
# 5. (Optional) VLC for audio speed control
brew install vlc
# 6. Run
python3 main.py
```

If `pip install` fails, try `pip install PyQt5 python-docx numpy soundfile python-vlc` instead.  
If the fallback audio player doesn't work, install `portaudio` via `brew install portaudio`.

### Linux (Debian/Ubuntu 22.04 or newer)

1. Download `CapsQual_1.6.0-linux.tar.gz`.
2. Open a terminal in the download folder and unfold the archive:
   ```bash
   tar -xzf CapsQual_1.6.0-linux.tar.gz
   ```
3. Make the extracted file executable:
   ```bash
   chmod +x CapsQual_1.6.0
   ```
4. Run the program:
   ```bash
   ./CapsQual_1.6.0
   ```
5. (Optional) Install VLC using your package manager (e.g., `sudo apt install vlc` on Debian/Ubuntu) to enable playback speed control.

To run from source (also required for Ubuntu < 22.04):

```bash
# 1. Install system dependencies
sudo apt update && sudo apt install -y python3-venv python3-pyqt5 portaudio19-dev
# 2. Clone the repository
git clone https://github.com/anouarg88/CapsQual.git
cd CapsQual
# 3. Create a virtual environment
python3 -m venv venv --system-site-packages
source venv/bin/activate
# 4. Install dependencies (If installation of pyaudio fails, make sure python-vlc is installed)
pip install -r requirements.txt
# 5. Run
python3 main.py
```

If `pip` is not installed, run `sudo apt install python3-pip` first.


If you encounter difficulties installing CapsQual, feel free to [open an issue](https://github.com/anouarg88/CapsQual/issues).

# Quickstart

This guide walks you through the basic workflow of CapsQual.  
Click any image to view it in full size.

---

## 1. Install CapsQual

Download the latest version from the [Releases page](https://github.com/anouarg88/CapsQual/releases)

For detailed setup instructions, see [Installation](#installation).

Prepare your subtitle files.  
If needed, check this tutorial on [how to install Whisper](https://www.qualitative-forschung.de/fqs-supplement/fotos/zoom/24-1-8-e_app1.pdf).

---

## 2. Import Audio & Subtitles

Import your files using the **Load Audio** button. If subtitle files are in the same folder, CapsQual will offer to import them automatically. Otherwise, they can be imported from the menu bar.

![Import Audio & Subtitles in CapsQual](https://github.com/user-attachments/assets/2a3030f0-ec5b-4a20-a1bd-3b65da2d92a4#gh-light-mode-only)
![Import Audio & Subtitles in CapsQual](https://github.com/user-attachments/assets/9be8710f-a231-48d4-b328-07c57c889b92#gh-dark-mode-only)

---

## 3. Assign Speakers

- Use the number keys (1, 2, 3, …) or buttons in the top-right corner to assign speakers to the selected segments.
- Add/remove speakers with the `+` / `−` buttons.
- Rename speakers using the text fields  

![Assign Speakers in CapsQual](https://github.com/user-attachments/assets/4f83680b-0d01-42d3-8456-bfd304fd7b2f#gh-light-mode-only)
![Assign Speakers in CapsQual](https://github.com/user-attachments/assets/98fb6702-4e72-4f11-b0e1-a217b81ac412#gh-dark-mode-only)

---

## 4. Auto-Process Transcript

Use **Modify transcript** to strip punctuation or convert everything to lowercase. CapsQual can also convert silent segments into pause symbols, if the subtitle files were created with ASR-software which supports _Voice Activity Detection_ (VAD), such as [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline) or [WhisperX](https://github.com/m-bain/WhisperX).

![Auto-Process Transcript in CapsQual](https://github.com/user-attachments/assets/b41a29fc-90a6-42e1-bfa6-f0be2e182989#gh-light-mode-only)
![Auto-Process Transcript in CapsQual](https://github.com/user-attachments/assets/fb9d77be-8afb-45b5-b741-7049d012c047#gh-dark-mode-only)

---

## 5. Review & Annotate

Review the transcript sequentially and split (`Space`), merge (`Del`) and edit (`E/F2`) segments where necessary. Edit timestamps (T) to adjust the start and end time of each segment if necessary. Use the **Symbols** button (`*`) to insert pauses, overlaps, comments and other transcription symbols. 


![Review & Annotate in CapsQual](https://github.com/user-attachments/assets/71ed0c77-61ac-49ab-9b66-cb01b96296d9#gh-light-mode-only)
![Review & Annotate in CapsQual](https://github.com/user-attachments/assets/468d326a-cb9a-47f0-9815-159cb9c15608#gh-dark-mode-only)

---

## 6. Export

Press the Export button or **Ctrl + Enter** to open the export dialog.

You can:
- Choose transcript conventions  
- Adjust formatting  
- Export as HTML, DOCX, TXT, or SRT  

![Export in CapsQual](https://github.com/user-attachments/assets/be82ffac-7271-4417-b021-03a6f52ccc35#gh-light-mode-only)
![Export in CapsQual](https://github.com/user-attachments/assets/655d2dcf-609c-4e1e-9cc0-584ec482e44f#gh-dark-mode-only)

---

# CLI Usage

CapsQual can also be used from the command line for headless conversion (Run from one directory level above CapsQual):

```bash
# Convert an SRT file to GAT2 transcript
python -m CapsQual transcript.srt

# Launch the GUI
python -m CapsQual -g

# TiQ format with auto-diarization (speaker names before colons)
python -m CapsQual input.srt -f tiq --speaker="$:"

# Export as HTML
python -m CapsQual input.srt -o transcript.html

# Customize layout
python -m CapsQual input.srt -f dresing_pehl --blank-lines
```

**Supported input formats:** `.srt`, `.vtt`, `.txt`, `.tsv`, `.json`  
**Output formats:** GAT2 (default), TiQ, Dresing & Pehl  
**Export types:** `.txt` (default), `.html`, `.docx`

For a full list of options, run `python -m CapsQual --help`.

For more info on how to use CapsQual, see the [CapsQual User Manual](https://github.com/anouarg88/CapsQual/wiki).

CapsQual was developed with the help of DeepSeek AI.
