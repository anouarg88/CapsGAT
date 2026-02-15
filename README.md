# CapsGAT

<img width="100" height="100" alt="capsgat_logo" src="https://github.com/user-attachments/assets/0f409c41-55a9-427d-9516-05532cc728be" />


CapsGAT is a lightweight tool for reformatting subtitle files (.SRT, .JSON, .TSV, .TXT) into qualitative interview transcripts based on the minimal version of GAT2 ([Gesprächsanalytisches Transkriptionssystem 2](https://gat-to.uni-jena.de/)). It enables users to assign speakers to segments quickly using keyboard shortcuts.


<img width="1702" height="992" alt="capsgat_v1.3_screenshot" src="https://github.com/user-attachments/assets/1257eeaa-ea9c-4a7d-9548-b41874e25ea6" />



Audio files can be imported and synced to the transcript. This is meant to reduce window-switching and simplify the formatting process. Playback speed can be adjusted (requires VLC Player to be installed). CapsGAT features basic GAT2-editing functionality such as segment splitting and merging, overlapping speech, pauses and comments. 

However, it is not meant as a replacement for professional transcription software (for full-fledged, professional transcription software, check out [EXMARaLDA](https://www.exmaralda.org); for AI-powered transcription with automatic diarization check out [noScribe](https://ai4culture.eu/resources/tools/172)), but more as a complementary formatting tool to be used with transcription AI models such as Whisper AI or CapsWriter.

CapsGAT projects can be loaded or saved. Transcripts can be exported as .HTML, .DOC, .TXT or .SRT files. With the exceptions of segments containing unassigned pauses and .SRT exports, only segments that have been assigned are included in the transcripts that are exported. The format for interview transcripts is based on the minimal GAT2 transcription convention, though many aspects (such as multiple tiers) are not implemented. A simpler transcription convention based on Dresing & Pehl can also be chosen for export formatting.


Please note that official CapsGAT releases are only available from this GitHub repository's ([releases page](https://github.com/anouarg88/CapsGAT/releases)). 
CapsGAT was developed using AI.
