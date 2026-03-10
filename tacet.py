#!/usr/bin/env python3
"""Trim MP3 audio: removes everything before a clap spike, silence after the clap, and trailing silence.

Uses only built-in Python modules + ffmpeg (no pydub dependency).
Compatible with Python 3.13+.
"""

import argparse
import array
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime
from pathlib import Path


def check_dependencies():
    """Check that ffmpeg is available."""
    if not shutil.which("ffmpeg"):
        print(
            "Error: ffmpeg is not installed.\n"
            "Install it with: brew install ffmpeg",
            file=sys.stderr,
        )
        sys.exit(1)


def mp3_to_wav(mp3_path: str) -> str:
    """Convert MP3 to a temporary WAV file. Returns the WAV path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", tmp.name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        os.unlink(tmp.name)
        print(f"Error converting {mp3_path} to WAV:\n{result.stderr}", file=sys.stderr)
        return None
    return tmp.name


def read_samples(wav_path: str) -> tuple[array.array, int]:
    """Read WAV samples as an array of signed 16-bit integers. Returns (samples, sample_rate)."""
    with wave.open(wav_path, "rb") as wf:
        n_frames = wf.getnframes()
        sample_rate = wf.getframerate()
        raw = wf.readframes(n_frames)
        samples = array.array("h", raw)
    return samples, sample_rate


def rms(samples: array.array, start: int, end: int) -> float:
    """Compute RMS amplitude for a slice of samples."""
    if start >= end:
        return 0.0
    total = sum(s * s for s in samples[start:end])
    return math.sqrt(total / (end - start))


def dbfs(rms_val: float) -> float:
    """Convert RMS to dBFS (relative to 16-bit max)."""
    if rms_val <= 0:
        return -120.0
    return 20 * math.log10(rms_val / 32768.0)


def find_clap(samples: array.array, sample_rate: int, chunk_ms: int = 5) -> int:
    """Find the clap (sudden loud spike) in the first 30 seconds. Returns position in ms."""
    chunk_size = int(sample_rate * chunk_ms / 1000)
    scan_end = min(len(samples), sample_rate * 30)

    # Compute average RMS
    overall_rms = rms(samples, 0, scan_end)
    overall_db = dbfs(overall_rms)

    # Find first chunk that's significantly louder than average
    max_amp = 0
    for i in range(0, scan_end, chunk_size):
        end = min(i + chunk_size, scan_end)
        chunk_max = max(abs(s) for s in samples[i:end])
        if chunk_max > max_amp:
            max_amp = chunk_max

    for i in range(0, scan_end, chunk_size):
        end = min(i + chunk_size, scan_end)
        chunk_rms = rms(samples, i, end)
        chunk_db = dbfs(chunk_rms)
        chunk_max = max(abs(s) for s in samples[i:end])

        if chunk_db > overall_db + 10 and chunk_max > max_amp * 0.5:
            return int(i * 1000 / sample_rate)

    # Fallback: use loudest peak
    print("  Warning: no clear clap detected, using loudest peak in first 30s", file=sys.stderr)
    max_val = 0
    max_pos = 0
    for i in range(0, scan_end, chunk_size):
        end = min(i + chunk_size, scan_end)
        chunk_max = max(abs(s) for s in samples[i:end])
        if chunk_max > max_val:
            max_val = chunk_max
            max_pos = i
    return int(max_pos * 1000 / sample_rate)


def find_speech_bounds(
    samples: array.array,
    sample_rate: int,
    silence_thresh_db: int = -40,
    min_silence_ms: int = 300,
) -> tuple[int, int]:
    """Find the start and end of speech (non-silent regions). Returns (start_ms, end_ms)."""
    chunk_ms = 10
    chunk_size = int(sample_rate * chunk_ms / 1000)
    total_chunks = len(samples) // chunk_size

    # Find all non-silent chunks
    non_silent_starts = []
    in_silence = True
    silence_chunks = 0
    min_silence_chunks = min_silence_ms // chunk_ms

    for i in range(total_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, len(samples))
        chunk_rms = rms(samples, start, end)
        chunk_db = dbfs(chunk_rms)

        if chunk_db > silence_thresh_db:
            if in_silence:
                non_silent_starts.append(i * chunk_ms)
            in_silence = False
            silence_chunks = 0
        else:
            silence_chunks += 1
            if silence_chunks >= min_silence_chunks:
                if not in_silence:
                    non_silent_starts.append(i * chunk_ms - (silence_chunks - 1) * chunk_ms)
                in_silence = True

    if not non_silent_starts:
        return 0, int(len(samples) * 1000 / sample_rate)

    # Find the first and last non-silent positions
    first_sound = non_silent_starts[0]

    # Scan from end to find last non-silent chunk
    last_sound = 0
    for i in range(total_chunks - 1, -1, -1):
        start = i * chunk_size
        end = min(start + chunk_size, len(samples))
        chunk_rms = rms(samples, start, end)
        chunk_db = dbfs(chunk_rms)
        if chunk_db > silence_thresh_db:
            last_sound = (i + 1) * chunk_ms
            break

    return first_sound, last_sound


def trim_with_ffmpeg(
    input_path: str,
    output_path: str,
    start_ms: int,
    end_ms: int,
):
    """Use ffmpeg to trim the audio file between start_ms and end_ms."""
    start_sec = start_ms / 1000.0
    duration_sec = (end_ms - start_ms) / 1000.0

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration_sec:.3f}",
            "-c:a", "libmp3lame",
            "-q:a", "2",
            output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error trimming {input_path}:\n{result.stderr}", file=sys.stderr)
        return False
    return True


def process_file(
    filepath: Path,
    output_dir: Path,
    silence_thresh_db: int,
    min_silence_ms: int,
    clap_duration_ms: int,
):
    """Process a single MP3 file."""
    print(f"Processing: {filepath.name}")

    # Convert to WAV for analysis
    wav_path = mp3_to_wav(str(filepath))
    if wav_path is None:
        return

    try:
        samples, sample_rate = read_samples(wav_path)
        total_ms = int(len(samples) * 1000 / sample_rate)
        print(f"  Duration: {total_ms}ms")

        # Find the clap
        clap_start = find_clap(samples, sample_rate)
        print(f"  Clap detected at {clap_start}ms")

        # Get samples after the clap + clap duration
        after_clap_ms = clap_start + clap_duration_ms
        after_clap_sample = int(after_clap_ms * sample_rate / 1000)
        remaining_samples = samples[after_clap_sample:]

        # Find speech bounds in the remaining audio
        speech_start, speech_end = find_speech_bounds(
            remaining_samples, sample_rate, silence_thresh_db, min_silence_ms
        )

        # Add padding
        padding = 50  # ms
        speech_start = max(0, speech_start - padding)
        speech_end = min(int(len(remaining_samples) * 1000 / sample_rate), speech_end + padding)

        # Calculate absolute positions
        abs_start = after_clap_ms + speech_start
        abs_end = after_clap_ms + speech_end
        print(f"  Speech region: {abs_start}ms - {abs_end}ms")

        # Trim with ffmpeg (keep original filename)
        out_path = output_dir / filepath.name
        if trim_with_ffmpeg(str(filepath), str(out_path), abs_start, abs_end):
            trimmed_duration = abs_end - abs_start
            print(f"  Saved: {out_path} ({trimmed_duration}ms)")

    finally:
        os.unlink(wav_path)


def main():
    check_dependencies()

    parser = argparse.ArgumentParser(description="Trim MP3: remove clap, leading/trailing silence")
    parser.add_argument("input", nargs="*", help="Input MP3 file(s) (default: all .mp3 in current directory)")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: trimmed_<timestamp>)")
    parser.add_argument("--silence-thresh", type=int, default=-40, help="Silence threshold in dB (default: -40)")
    parser.add_argument("--min-silence", type=int, default=300, help="Minimum silence length in ms (default: 300)")
    parser.add_argument("--clap-duration", type=int, default=200, help="Expected clap duration in ms (default: 200)")
    args = parser.parse_args()

    files = args.input or sorted(str(p) for p in Path(".").glob("*.mp3"))
    if not files:
        print("No MP3 files found in current directory.", file=sys.stderr)
        sys.exit(1)

    # Create timestamped output directory
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(f"trimmed_{timestamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}\n")

    for filepath in files:
        path = Path(filepath)
        if not path.exists():
            print(f"Skipping {filepath}: file not found", file=sys.stderr)
            continue

        process_file(
            path,
            out_dir,
            silence_thresh_db=args.silence_thresh,
            min_silence_ms=args.min_silence,
            clap_duration_ms=args.clap_duration,
        )


if __name__ == "__main__":
    main()
