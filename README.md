# CapsGAT

<img width="100" height="100" alt="capsgat_logo" src="https://github.com/user-attachments/assets/c45c77bf-3dfc-46db-957b-55746d3c7371" />

CapsGAT is a lightweight tool for reformatting subtitle files (.SRT, .JSON, .TSV, .TXT) into qualitative interview transcripts based on the minimal version of GAT2 ([Gesprächsanalytisches Transkriptionssystem 2](https://gat-to.uni-jena.de/)). It enables users to assign speakers to segments quickly using keyboard shortcuts.


<img width="1809" height="990" alt="capsgat_v1.2_screenshot" src="https://github.com/user-attachments/assets/be0b0b89-e837-4cb2-809b-0ba4091568cc" />



Audio files can be imported and synced to the transcript. This is meant to reduce window-switching and simplify the formatting process. Playback speed can be adjusted (requires VLC Player to be installed). CapsGAT features basic GAT2-editing functionality such as segment splitting and merging, overlapping speech, pauses and comments. 

However, it is not meant as a replacement for professional transcription software (for full-fledged, professional transcription software, check out [EXMARaLDA](https://www.exmaralda.org); for AI-powered transcription with automatic diarization check out [noScribe](https://ai4culture.eu/resources/tools/172)), but more as a complementary formatting tool to be used with transcription AI models such as Whisper AI or CapsWriter.

CapsGAT projects can be loaded or saved. Transcripts can be exported as .HTML, .DOC, .TXT or .SRT files. With the exceptions of segments containing unassigned pauses and .SRT exports, only segments that have been assigned are included in the transcripts that are exported. The format for interview transcripts is based on the minimal GAT2 transcription convention, though many aspects (such as multiple tiers) are not implemented. A simpler transcription convention based on Dresing & Pehl can also be chosen for export formatting.


Please note that official CapsGAT releases are only available from this GitHub repository's ([releases page](https://github.com/anouarg88/CapsGAT/releases)). 
CapsGAT was developed using AI.
