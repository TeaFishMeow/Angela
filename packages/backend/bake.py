from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np


def bake_visemes(input_wav: Path, output_json: Path, scene_id: str, fps: int = 30) -> None:
    y, sr = librosa.load(input_wav, sr=22050, mono=True)
    hop = max(1, sr // fps)
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=hop)[0]
    peak = max(float(np.quantile(rms, 0.95)), 1e-6)
    open_y = np.clip(rms / peak, 0, 1)
    open_y = np.convolve(open_y, np.ones(3) / 3, mode="same")
    frames = [[round(float(value), 3)] for value in open_y]
    payload = {
        "scene": scene_id,
        "fps": fps,
        "params": ["ParamMouthOpenY"],
        "start": 0.0,
        "frames": frames,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bake Live2D mouth-open visemes from a digital-human vocal wav (RMS@fps)."
    )
    parser.add_argument("input_wav", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--scene", default="chuanqi")
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    bake_visemes(args.input_wav, args.output_json, args.scene, args.fps)


if __name__ == "__main__":
    main()
