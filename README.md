# Tacet
*Cut the quiet*

An audio processing tool that automatically trims MP3 files by detecting a clap spike at the beginning and removing leading/trailing silence. Designed for processing voice recordings (lectures, interviews, etc.) marked with a clap to indicate the start.

## How It Works

1. Detects a loud clap spike in the first 30 seconds of audio
2. Removes everything before the clap (plus a configurable buffer)
3. Identifies and removes silence after the clap
4. Removes trailing silence from the end
5. Adds small padding (50ms) for natural boundaries

## Requirements

- Python 3.13+
- [ffmpeg](https://ffmpeg.org/)

```bash
# macOS
brew install ffmpeg
```

## Usage

```bash
# Process all MP3 files in current directory
python3 trim_audio.py

# Process specific files
python3 trim_audio.py file1.mp3 file2.mp3

# Custom output directory
python3 trim_audio.py -o ./output

# Adjust sensitivity
python3 trim_audio.py --silence-thresh -35 --min-silence 500
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `input` | all `.mp3` in cwd | MP3 file(s) to process |
| `-o, --output-dir` | `trimmed_<timestamp>` | Output directory |
| `--silence-thresh` | `-40` | Silence threshold in dB |
| `--min-silence` | `300` | Minimum silence duration in ms |
| `--clap-duration` | `200` | Expected clap duration in ms |

Output files are saved to a timestamped directory (`trimmed_YYYYMMDD_HHMMSS/`) by default, preserving original filenames.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
