#!/usr/bin/env python3
"""Bake a source vocal through an RVC model."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from rvc_python.infer import RVCInference


def main() -> int:
    parser = argparse.ArgumentParser(description="Bake vocals with RVC.")
    parser.add_argument("--model", required=True, help="Path to the RVC .pth model.")
    parser.add_argument("--index", default="", help="Optional path to the RVC .index file.")
    parser.add_argument("--input", required=True, help="Source vocal wav.")
    parser.add_argument("--output", required=True, help="Output RVC vocal wav.")
    parser.add_argument("--device", default="cuda:0", help="cuda:0 or cpu:0.")
    parser.add_argument("--pitch", type=int, default=0, help="f0up_key in semitones.")
    parser.add_argument("--f0", default="rmvpe", choices=["harvest", "crepe", "rmvpe", "pm"])
    parser.add_argument("--index_rate", type=float, default=0.6, help="Index blend ratio, 0-1.")
    parser.add_argument("--protect", type=float, default=0.33, help="Consonant protection, 0-0.5.")
    parser.add_argument("--filter_radius", type=int, default=3)
    args = parser.parse_args()

    model_path = Path(args.model).resolve()
    index_path = Path(args.index).resolve() if args.index else None
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[bake_rvc] model={model_path}")
    print(f"[bake_rvc] input={input_path} -> output={output_path}")
    print(
        f"[bake_rvc] device={args.device} pitch={args.pitch} f0={args.f0} "
        f"index_rate={args.index_rate} protect={args.protect}"
    )

    # rvc-python 0.1.0 discovers models as <models_dir>/<model_name>/*.pth.
    models_dir = str(model_path.parent.parent)
    model_name = model_path.parent.name
    rvc = RVCInference(models_dir=models_dir, device=args.device)
    rvc.models[model_name] = {
        "pth": str(model_path),
        "index": str(index_path) if index_path else None,
    }
    rvc.load_model(model_name, version="v2")
    rvc.set_params(
        f0up_key=args.pitch,
        f0method=args.f0,
        index_rate=args.index_rate,
        protect=args.protect,
        filter_radius=args.filter_radius,
    )
    rvc.infer_file(str(input_path), str(output_path))
    print(f"[bake_rvc] OK -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
