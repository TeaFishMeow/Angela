"""原声版烤制（RVC 引擎未就绪时的可播兜底，docs/09 §8）。

对每首曲：
  1) ffmpeg 预混 伴奏 + 原始人声 → backing.wav（队友C 现场声部不在带里）
  2) 由原始人声用 numpy RMS@30fps → visemes.json（数字人对口型用）

注意：这是"原声版"——音色是原唱、不是数字人 RVC 音色。
RVC 引擎(torch/rvc)装好后，改走 rvc.py 真变声再预混，得到数字人音色 backing.wav。
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[3] / "演示用例"

JOBS = [
    # name, instrumental, vocal, backing, visemes_out, scene_id
    ("传奇", "传奇_分轨/传奇_instrumental.wav", "传奇_分轨/传奇_vocals.wav",
     "传奇_分轨/传奇_backing.wav", "传奇_分轨/visemes.json", "chuanqi"),
    ("因为爱情", "因为爱情_分轨/因为爱情 男声_instrumental.wav", "因为爱情_分轨/因为爱情 男声_vocals.wav",
     "因为爱情_分轨/因为爱情_backing.wav", "因为爱情_分轨/visemes.json", "yinwei-aiqing"),
]


def ffprobe_dur(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def bake_visemes(vocal: Path, out: Path, scene_id: str, fps: int = 30) -> int:
    y, sr = sf.read(str(vocal), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    hop = max(1, sr // fps)
    n = (len(y) // hop) * hop
    rms = np.sqrt(np.mean(y[:n].reshape(-1, hop) ** 2, axis=1)) if n > 0 else np.zeros(1)
    peak = max(float(np.quantile(rms, 0.95)), 1e-6)
    open_y = np.convolve(np.clip(rms / peak, 0, 1), np.ones(3) / 3, mode="same")
    payload = {"scene": scene_id, "fps": fps, "params": ["ParamMouthOpenY"], "start": 0.0,
               "frames": [[round(float(v), 3)] for v in open_y]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return len(open_y)


def mix(instrumental: Path, vocal: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    flt = ("[0:a]volume=0.88[bg];"
           "[1:a]volume=0.95,aresample=async=1[v];"
           "[bg][v]amix=inputs=2:duration=longest:dropout_transition=0[m]")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(instrumental), "-i", str(vocal),
         "-filter_complex", flt, "-map", "[m]", "-ac", "2", "-ar", "44100", str(output)],
        check=True, capture_output=True,
    )


def main() -> None:
    for name, inst, voc, back, vis, sid in JOBS:
        inst_p, voc_p = ROOT / inst, ROOT / voc
        back_p, vis_p = ROOT / back, ROOT / vis
        if not inst_p.exists() or not voc_p.exists():
            print(f"[skip] {name}: 缺素材 inst={inst_p.exists()} voc={voc_p.exists()}")
            continue
        mix(inst_p, voc_p, back_p)
        n = bake_visemes(voc_p, vis_p, sid)
        print(f"[OK] {name}: backing={ffprobe_dur(back_p):.1f}s  visemes={n}帧  "
              f"(vocal={ffprobe_dur(voc_p):.1f}s, inst={ffprobe_dur(inst_p):.1f}s)")


if __name__ == "__main__":
    main()
