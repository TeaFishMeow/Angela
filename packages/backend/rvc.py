from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def infer(
    input_wav: Path,
    output_wav: Path,
    model: Path,
    index: Path | None = None,
    pitch_shift: int = 12,
    f0_method: str = "rmvpe",
) -> None:
    rvc = shutil.which("rvc")
    if rvc is None:
        raise RuntimeError("未找到 rvc CLI。请先安装 Applio/RVC，并确认 `rvc` 在 PATH 中。")

    cmd = [
        rvc,
        "infer",
        "-m",
        str(model),
        "-i",
        str(input_wav),
        "-o",
        str(output_wav),
        "-p",
        str(pitch_shift),
        "-f0",
        f0_method,
    ]
    if index:
        cmd.extend(["-ir", str(index)])
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Thin wrapper around Applio/RVC inference.")
    parser.add_argument("input_wav", type=Path)
    parser.add_argument("output_wav", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--pitch-shift", type=int, default=12)
    parser.add_argument("--f0-method", default="rmvpe")
    args = parser.parse_args()
    infer(args.input_wav, args.output_wav, args.model, args.index, args.pitch_shift, args.f0_method)


if __name__ == "__main__":
    main()
