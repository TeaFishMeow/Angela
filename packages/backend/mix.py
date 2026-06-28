from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def mix(
    instrumental: Path,
    vocal_rvc: Path,
    output: Path,
    bg_volume: float = 0.88,
    vocal_volume: float = 0.95,
) -> None:
    """Premix the backing track: instrumental + digital-human RVC vocal.

    队友C 现场唱的声部**不进带**（走调音台 PA）。见 docs/04 §5。
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"[0:a]volume={bg_volume}[bg];"
        f"[1:a]volume={vocal_volume},aresample=async=1[v];"
        "[bg][v]amix=inputs=2:duration=longest:dropout_transition=0[m]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(instrumental),
        "-i",
        str(vocal_rvc),
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
    parser = argparse.ArgumentParser(
        description="Premix backing.wav = instrumental + digital-human RVC vocal (teammateC not included)."
    )
    parser.add_argument("instrumental", type=Path)
    parser.add_argument("vocal_rvc", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    mix(args.instrumental, args.vocal_rvc, args.output)


if __name__ == "__main__":
    main()
