# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tacet is a single-script Python CLI tool that trims MP3 files by detecting a clap spike and removing leading/trailing silence. It uses only Python stdlib + ffmpeg (no pydub or other audio libraries).

## Running

```bash
# Process all MP3s in current directory
python3 tacet.py

# Process specific files with options
python3 tacet.py file.mp3 -o ./output --silence-thresh -35 --min-silence 500
```

Requires Python 3.13+ and ffmpeg (`brew install ffmpeg` on macOS).

## Architecture

Single file (`tacet.py`) with a linear processing pipeline:

1. **MP3 → WAV conversion** (`mp3_to_wav`): ffmpeg converts to mono 44100Hz 16-bit WAV in a temp file for analysis
2. **Clap detection** (`find_clap`): Scans first 30s for a chunk significantly louder than average RMS (10dB+ above mean, 50%+ of max amplitude)
3. **Speech boundary detection** (`find_speech_bounds`): Identifies non-silent regions using RMS-based silence detection with configurable threshold and minimum duration
4. **Trimming** (`trim_with_ffmpeg`): Re-encodes the relevant portion back to MP3 using ffmpeg with libmp3lame

Audio analysis uses `array.array("h")` for 16-bit signed samples. RMS/dBFS calculations are in `rms()` and `dbfs()` helper functions.
