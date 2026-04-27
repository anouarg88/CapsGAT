# CapsQual
![GitHub Release](https://img.shields.io/github/v/release/anouarg88/CapsQual?label=Latest%20release)
[![Run CI tests](https://github.com/anouarg88/CapsQual/actions/workflows/tests.yml/badge.svg)](https://github.com/anouarg88/CapsQual/actions/workflows/tests.yml)



CapsQual (formerly CapsGAT) is an open source cross-platform UI-tool for editing and reformatting subtitle files (.SRT, .JSON, .TSV, .TXT) into qualitative interview transcripts based on different conventions such as the minimal version of GAT2 ([Gesprächsanalytisches Transkriptionssystem 2](https://gat-to.uni-jena.de/)), TiQ (Talk in Qualitative Research) and those suggested by Kuckartz and Dresing & Pehl. It enables users to assign speakers to segments quickly using keyboard shortcuts. Audio files can be imported and synced to the transcript. This is meant to reduce window-switching and simplify the formatting process. Playback speed can be adjusted (requires VLC Player to be installed). CapsQual features essential transcript-editing functionality such as segment splitting and merging, customizable symbols, overlapping speech, pauses, comments and more.  


However, it is not meant as a replacement for dedicated manual transcription software (for full-fledged, professional transcription software, check out [EXMARaLDA](https://www.exmaralda.org)), nor as an all-in-one automated transcription worksuite (for AI-powered transcription with automatic diarization check out [noScribe](https://ai4culture.eu/resources/tools/172)), but as a complementary formatting tool to be used with transcription AI models such as Whisper AI or CapsWriter, aimed at those who wish to efficiently tidy up their automatically transcribed interview-data in a user-friendly, intuitive environment. Projects can be loaded or saved. Transcripts can be exported as .HTML, .DOCX, .TXT or .SRT files.

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

<img src="https://github.com/user-attachments/assets/63114a9b-4a62-466c-a5dc-81ab742f9138" alt="import" />

---

## 3. Assign Speakers

- Use the number keys (1, 2, 3, …) or buttons in the top-right corner to assign speakers to the selected segments.
- Add/remove speakers with the `+` / `−` buttons.
- Rename speakers using the text fields  

<img src="https://github.com/user-attachments/assets/550bac64-003a-44c5-994b-f36c1cdedb58" alt="assign" />

---

## 4. Auto-Process Transcript

Use **Modify transcript** to strip punctuation or convert everything to lowercase. CapsQual can also convert silent segments into pause symbols, if the subtitle files were created with ASR-software which supports _Voice Activity Detection_ (VAD), such as [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline) or [WhisperX](https://github.com/m-bain/WhisperX).

<img src="https://github.com/user-attachments/assets/8373c360-0428-4404-ad39-771d196a15c9" alt="modify" />

---

## 5. Review & Annotate

Review the transcript sequentially and split (`Space`), merge (`Del`) and edit (`E/F2`) segments where necessary. Edit timestamps (T) to adjust the start and end time of each segment if necessary. Use the **Symbols** button (`*`) to insert pauses, overlaps, comments and other transcription symbols. 

<img src="https://github.com/user-attachments/assets/04d96b86-706b-4a58-acf0-4c1496b554da" alt="symbols" />

---

## 6. Export

Press the Export button or **Ctrl + Enter** to open the export dialog.

You can:
- Choose transcript conventions  
- Adjust formatting  
- Export as HTML, DOCX, TXT, or SRT  

<img src="https://github.com/user-attachments/assets/0ada3395-1d61-4bdd-8586-9bd36234eb24" alt="export" />

---

For more details, see the [CapsQual User Manual](https://github.com/anouarg88/CapsQual/wiki).

CapsQual was developed using AI.

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

_Note: Version 1.5.1 has been used as an example in this installation guide. Please replace "1.5.1" with whichever version you are going to install._

### Windows

1. Download the Windows installer `CapsQual_1.5.1_Setup.exe` or the portable executable: `CapsQual_1.5.1.exe`.
2. If you downloaded the installer, double‑click and follow the on‑screen instructions.
3. If you downloaded the portable version, simply unzip the file in any folder and double‑click `CapsQual_1.5.1.exe` to run. A system warning may show up, since this software does not contain any official certificates. You may ignore this at your own discretion.
4. (Optional) Install [VLC](https://www.videolan.org/) to enable playback speed control and better audio compatibility before running CapsQual.

### macOS

Two versions are provided:

- `CapsQual-macOS-Intel` for Intel‑based Macs (2019 and earlier)
- `CapsQual-macOS-AppleSilicon` for Macs with Apple Silicon (M1, M2, M3)

1. Download the appropriate `.zip` file.
2. Open the downloaded file and drag `CapsQual_1.5.1.app` to your `Applications` folder.
3. The first time you run the app, macOS may warn you that it is from an unidentified developer.  
   To bypass this, right‑click (or Ctrl‑click) the app and select **Open**, then click **Open** again.
4. (Optional) Install [VLC](https://www.videolan.org/) to enable playback speed control before running CapsQual.

### Linux (Debian/Ubuntu 22.04 or newer)

1. Download `CapsQual_1.5.1-linux.tar.gz`.
2. Open a terminal in the download folder and unfold the archive:
   ```bash
   tar -xzf CapsQual_1.5.1-linux.tar.gz
   ```
3. Make the extracted file executable:
   ```bash
   chmod +x CapsQual_1.5.1
   ```
4. Run the program:
   ```bash
   ./CapsQual_1.5.1
   ```
5. (Optional) Install VLC using your package manager (e.g., `sudo apt install vlc` on Debian/Ubuntu) to enable playback speed control.

For Ubuntu versions < 22.04, run from source (see below).

### Running CapsQual from Source

***Linux:***

1. Install system dependencies

   Open a terminal and run:
   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-pyqt5 portaudio19-dev
   ```
 
2. Clone the repository:
   ```bash
   git clone https://github.com/anouarg88/CapsQual.git
   cd CapsQual
   ```
   (Or download and unpack the archive from this release page.)

3. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv --system-site-packages
   source venv/bin/activate
   ```
4. Install python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   If you don't have pip installed, run ```sudo apt install python3-pip``` first.
   
6. Run the application:
   ```bash
   python3 main.py
   ```

***macOS:***

1. Install Python 3.9 or later** (e.g., via [Homebrew](https://brew.sh/):).

   Open a terminal and run:
   ```bash/zsh
   brew install python
   ```
3. Clone the repository:
   ```bash/zsh
   git clone https://github.com/anouarg88/CapsQual.git
   ```
4. Create a virtual environment (recommended):
   ```bash/zsh
   cd CapsQual
   python3 -m venv venv
   source venv/bin/activate
   ```

5. Install python dependencies
   ```bash/zsh
   pip install -r requirements.txt
   ```
   (If installing dependencies from requirements.txt fails, which it might for some versions, run `PyQt5 python-docx numpy soundfile python-vlc` instead. Note that the fallback audio player will not be available - see step 4.)
   
4. Install VLC for full audio support (optional but highly recommended)
   ```bash
   brew install vlc
   ```
   
5. Run the application:
   ```bash
   python3 main.py
   ```
   (On macOS, you may need to install `portaudio` via Homebrew if you want a fallback audio player: `brew install portaudio`. If the fallback audio player does not work, instlall VLC using: `brew install vlc`.)


***Windows:***
1. Install Python 3.9 or later from [python.org](https://www.python.org/downloads/). During installation, make sure to check “Add Python to PATH”.

2. Clone the repository
   Open a command prompt (or Powershell):
   ```cmd
   git clone https://github.com/anouarg88/CapsQual.git
   ```

4. Create a virtual environment (recommended)
   ```cmd
   cd CapsQual
   python -m venv venv
   venv\Scripts\activate
   ```
   
5. Install python dependencies
   ```cmd
   pip install -r requirements.txt
   ```
   
8. Run the application:
   ```cmd
   python main.py
   ```


If you encounter difficulties installing CapsQual, feel free to [open an issue](https://github.com/anouarg88/CapsQual/issues).
