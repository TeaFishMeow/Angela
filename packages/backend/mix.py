from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def mix(
    instrumental: Path,
    angela: Path,
    neo: Path,
    output: Path,
    bg_volume: float = 0.85,
    angela_volume: float = 0.9,
    neo_volume: float = 0.8,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"[1:a]volume={angela_volume}[a];"
        f"[2:a]volume={neo_volume},aresample=async=1[n];"
        f"[0:a]volume={bg_volume}[bg];"
        "[bg][a][n]amix=inputs=3:duration=longest:dropout_transition=0[m]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(instrumental),
        "-i",
        str(angela),
        "-i",
        str(neo),
        "-filter_complex",
        filter_complex,
        "-map",
        "[m]",
        "-ac",
        "2",
        "-ar",
        "44100",
        str(output),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mix instrumental + Angela RVC vocal + Neo vocal.")
    parser.add_argument("instrumental", type=Path)
    parser.add_argument("angela", type=Path)
    parser.add_argument("neo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    mix(args.instrumental, args.angela, args.neo, args.output)


if __name__ == "__main__":
    main()
