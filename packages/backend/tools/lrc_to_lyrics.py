"""
LRC -> lyrics.json 转换器（Angela 合唱模式）
============================================
把带时间戳的 .lrc 转成 docs/03 规范的 lyrics.json：
  { scene, fps, lines:[ {t, d, part, performer, text} ] }

用法：
  python lrc_to_lyrics.py <曲名lrc> <scene_id> <输出json> [--offset 秒] [--relation unison|duet]

说明：
- 时间戳来自原曲；RVC 不改变时长，故与伴奏带(backing.wav)时间轴基本一致。
- backing.wav 若与原曲起点不同，用 --offset 整体平移（联调时按波形微调）。
- 传奇(unison)：所有行 part=duet（Angela+队友C 齐唱）。
- 因为爱情(duet)：副歌(因为爱情/所以…)=duet；主歌按原唱男女交替
  digital(陈奕迅→Neo)/teammateC(王菲→队友C)起；★该 LRC 把部分男女行合并，
  故 part 仅供初排，务必人工校对（输出带 _part_needs_review）。
- 每行 d 按文本长度估、且不超过到下一句的间隔，避免间奏时一句滞留。
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
META = ("作词", "作曲", "编曲", "制作人", "演唱", "和声", "吉他", "贝斯", "鼓", "钢琴", "弦乐")


def parse_lrc(path: Path):
    """返回 [(t秒, text)]，跳过元数据与空行。"""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = list(TS.finditer(line))
        if not m:
            continue
        text = line[m[-1].end():].strip()
        mm, ss = m[-1].group(1), m[-1].group(2)
        t = int(mm) * 60 + float(ss)
        if not text or any(text.startswith(k) for k in META):
            continue
        out.append((t, text))
    return out


def est_dur(text: str, gap: float, cap: float = 6.0) -> float:
    """按字数估演唱时长，且不超过到下一句的间隔。"""
    est = max(1.5, len(text) * 0.22 + 0.8)
    return round(min(est, gap if gap > 0 else cap, cap), 2)


def assign_part(text: str, idx_in_verse: int, relation: str) -> tuple[str, str]:
    if relation == "unison":
        return "duet", "Angela+队友C"
    # duet：副歌判定
    if text.startswith(("因为爱情", "所以")):
        return "duet", "Neo+队友C"
    # 主歌男女交替，digital(Neo 男) 起
    part = "digital" if idx_in_verse % 2 == 0 else "teammateC"
    perf = "Neo" if part == "digital" else "队友C"
    return part, perf


def build(lines, scene_id: str, relation: str, offset: float):
    out = []
    verse_i = 0  # 主歌男女交替计数（M=digital 起）；遇副歌或合并行调整
    MERGED = 12  # duet 主歌里 >=该字数通常是把男女两行合并了
    for i, (t, text) in enumerate(lines):
        gap = (lines[i + 1][0] - t) if i + 1 < len(lines) else 4.0
        is_chorus = relation == "duet" and text.startswith(("因为爱情", "所以", "依然"))
        if is_chorus:
            part, perf = "duet", "Neo+队友C"      # 副歌：两人合唱，不消耗交替计数
        elif relation == "duet" and len(text) >= MERGED:
            part, perf = "duet", "Neo+队友C"      # 合并行：实为男女各半
            verse_i += 2                          # 消耗 M、F 两个槽，保持后续对齐
        else:
            part, perf = assign_part(text, verse_i, relation)
            verse_i += 1
        out.append({
            "t": round(t + offset, 2),
            "d": est_dur(text, gap),
            "part": part,
            "performer": perf,
            "text": text,
        })
    return {"scene": scene_id, "fps": 30, "lines": out,
            "_part_needs_review": relation == "duet"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lrc")
    ap.add_argument("scene_id")
    ap.add_argument("out")
    ap.add_argument("--offset", type=float, default=0.0, help="整体时间平移(秒)")
    ap.add_argument("--relation", choices=["unison", "duet"], default="unison")
    a = ap.parse_args()

    lines = parse_lrc(Path(a.lrc))
    if not lines:
        sys.exit("未解析到歌词时间戳")
    data = build(lines, a.scene_id, a.relation, a.offset)
    Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台小结（ASCII-safe，兼容 Windows GBK 控制台）
    from collections import Counter
    c = Counter(x["part"] for x in data["lines"])
    print(f"[OK] {a.lrc}  ->  {a.out}")
    print(f"  scene={a.scene_id} relation={a.relation} offset={a.offset}s lines={len(data['lines'])}")
    print(f"  parts: {dict(c)}")
    if data.get("_part_needs_review"):
        print("  [!] duet: part is a first-pass guess; verify male/female by ear (merged lines esp.)")


if __name__ == "__main__":
    main()
