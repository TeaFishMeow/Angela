#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预混伴奏带 backing.wav = 伴奏 instrumental + 数字人声 vocal_rvc。
对应 docs/04 §5、docs/07 §5。队友C 唱的部分不在带里。

关键：backing / vocal_rvc / 轨道 JSON 同起点 0，勿单独 trim。
用法：
  python premix_backing.py \
    --instrumental "../../演示用例/传奇_分轨/传奇_instrumental.wav" \
    --vocal_rvc    "../../演示用例/传奇_分轨/传奇_vocals_angela_rvc.wav" \
    --output       "../../演示用例/传奇_分轨/传奇_backing.wav" \
    --inst_vol 0.85 --vocal_vol 0.95
"""
import argparse
import subprocess
import sys


def premix(instrumental, vocal_rvc, output, inst_vol, vocal_vol, sr):
    fc = (
        f"[0:a]volume={inst_vol}[a];"
        f"[1:a]volume={vocal_vol},aresample=async=1[b];"
        f"[a][b]amix=inputs=2:duration=longest[m]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", instrumental,
        "-i", vocal_rvc,
        "-filter_complex", fc,
        "-map", "[m]",
        "-ac", "2", "-ar", str(sr),
        output,
    ]
    print("[premix] " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[premix] OK -> {output}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="预混伴奏带 backing.wav")
    ap.add_argument("--instrumental", required=True)
    ap.add_argument("--vocal_rvc", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--inst_vol", type=float, default=0.85, help="伴奏音量 docs 传奇0.85/因为爱情0.9")
    ap.add_argument("--vocal_vol", type=float, default=0.95, help="人声音量")
    ap.add_argument("--sr", type=int, default=44100)
    args = ap.parse_args()
    sys.exit(premix(args.instrumental, args.vocal_rvc, args.output,
                    args.inst_vol, args.vocal_vol, args.sr))
