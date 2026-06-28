#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烘焙口型 visemes.json：对数字人 RVC 人声逐帧 RMS@30fps。docs/03 §3、docs/04 §6。
只烘焙数字人声部（队友C 是真人，不对口型）。归一化按 0.95 分位 + 三帧平滑。
用法：
  python bake_visemes.py \
    --vocal_rvc "../../演示用例/传奇_分轨/传奇_vocals_angela_rvc.wav" \
    --output    "../../演示用例/传奇_分轨/visemes.json" \
    --scene chuanqi
"""
import argparse
import json
import librosa
import numpy as np


def bake(vocal_rvc, output, scene, fps):
    y, sr = librosa.load(vocal_rvc, sr=22050, mono=True)
    hop = sr // fps
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=hop)[0]
    peak = max(np.quantile(rms, 0.95), 1e-6)
    open_y = np.convolve(np.clip(rms / peak, 0, 1), np.ones(3) / 3, mode="same")
    data = {
        "scene": scene,
        "fps": fps,
        "params": ["ParamMouthOpenY"],
        "start": 0.0,
        "frames": [[round(float(v), 3)] for v in open_y],
    }
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[visemes] OK {len(open_y)} frames ({len(open_y)/fps:.1f}s) -> {output}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="烘焙口型 visemes.json")
    ap.add_argument("--vocal_rvc", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()
    bake(args.vocal_rvc, args.output, args.scene, args.fps)
