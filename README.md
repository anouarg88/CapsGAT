# CapsQual

<img width="100" height="100" alt="CapsQual logo" src="https://github.com/user-attachments/assets/db350747-b876-45b8-b90d-341adc87b179" />


CapsQual (formerly CapsGAT) is a keyboard-first, lightweight UI-tool for editing and reformatting subtitle files (.SRT, .JSON, .TSV, .TXT) into qualitative interview transcripts based on different conventions such as the minimal version of GAT2 ([Gesprächsanalytisches Transkriptionssystem 2](https://gat-to.uni-jena.de/)), TiQ (Talk in Qualitative Research) and those suggested by Dresing & Pehl and by Kuckartz. It enables users to assign speakers to segments quickly using keyboard shortcuts.

![CapsQual 1.5 Screenshot](https://github.com/user-attachments/assets/46caf499-e679-4e41-a48f-e8e03434eeba#gh-light-mode-only)
![CapsQual 1.5 Screenshot](https://github.com/user-attachments/assets/70429fe9-9184-448d-9bc2-418e6519160d#gh-dark-mode-only)



Audio files can be imported and synced to the transcript. This is meant to reduce window-switching and simplify the formatting process. Playback speed can be adjusted (requires VLC Player to be installed). CapsQual features basic transcript-editing functionality such as segment splitting and merging, customizable symbols, overlapping speech, pauses, comments and more.  


However, it is not meant as a replacement for professional manual transcription software (for full-fledged, professional transcription software, check out [EXMARaLDA](https://www.exmaralda.org)), nor as an all-in-one automated transcription worksuite (for AI-powered transcription with automatic diarization check out [noScribe](https://ai4culture.eu/resources/tools/172)), but more as a complementary formatting tool to be used with transcription AI models such as Whisper AI or CapsWriter, aimed at those who wish to efficiently tidy up their automatically transcribed interview-data in a user-friendly, intuitive environment. Projects can be loaded or saved. Transcripts can be exported as .HTML, .DOCX, .TXT or .SRT files. With the exceptions of segments containing unassigned pauses and .SRT exports, only segments that have been assigned are included in the transcripts that are exported.

For further instructions on how to use CapsQual, please refer to the [CapsQual User Manual](https://github.com/anouarg88/CapsQual/wiki). Please note that official CapsQual releases are only available from this GitHub repository's [Releases page](https://github.com/anouarg88/CapsGAT/releases). 
CapsQual was developed using AI.

# Contributions

Contributions are welcome! If you would like to contribute to CapsQual, please start by opening an issue or responding to an existing one to discuss your ideas before starting work. This helps ensure your efforts align with the project's goals. For code contributions, please fork the repository and submit a pull request after the idea has been discussed. Thank you for your interest!

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
   If you don't have pip installed, run ```sudo apt install python3-pip``` first.

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
5. Run the application:
   ```bash
   python3 main.py
   ```

***macOS:***

1. **Install Python 3.9 or later** (e.g., via [Homebrew](https://brew.sh/): `brew install python`).
2. **Open Terminal** and run:
   ```bash
   git clone https://github.com/anouarg88/CapsQual.git
   cd CapsQual
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Run the application**:
   ```bash
   python main.py
   ```
   (On macOS, you may need to install `portaudio` via Homebrew if you want a fallback audio player: `brew install portaudio`.)


***Windows:***
1. **Install Python 3.9 or later** from [python.org](https://www.python.org/downloads/). During installation, check **“Add Python to PATH”**.
2. **Open Command Prompt** (or PowerShell) and install dependencies:
   ```cmd
   git clone https://github.com/anouarg88/CapsQual.git
   cd CapsQual
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Run the application**:
   ```cmd
   python main.py
   ```

For help on how to use CapsQual see the CapsQual Wiki on Github or press `F1` in CapsQual.
