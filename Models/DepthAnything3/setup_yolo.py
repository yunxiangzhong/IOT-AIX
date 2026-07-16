from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download YOLO26m and optionally export a local FP16 TensorRT engine")
    parser.add_argument("--weights-dir", type=Path, required=True)
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args()

    weights_dir = args.weights_dir.resolve()
    weights_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(weights_dir)

    import torch
    from ultralytics import YOLO, __version__ as ultralytics_version

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; refusing to download a CPU-only deployment")

    pt_path = weights_dir / "yolo26m.pt"
    model = YOLO(str(pt_path) if pt_path.is_file() else "yolo26m.pt", task="detect")
    resolved_pt = Path(getattr(model, "ckpt_path", pt_path)).resolve()
    if not pt_path.is_file() and resolved_pt.is_file():
        shutil.copy2(resolved_pt, pt_path)
        model = YOLO(str(pt_path), task="detect")
    if not pt_path.is_file():
        raise FileNotFoundError(f"YOLO26m download did not create {pt_path}")

    engine_path: Path | None = None
    if not args.skip_export:
        exported = model.export(
            format="engine",
            imgsz=512,
            device=0,
            quantize=16,
            batch=1,
            dynamic=False,
            workspace=2,
            nms=False,
        )
        exported_path = Path(exported).resolve()
        engine_path = weights_dir / "yolo26m.engine"
        if exported_path != engine_path:
            shutil.copy2(exported_path, engine_path)

    print(json.dumps({
        "ultralytics": ultralytics_version,
        "cuda_device": torch.cuda.get_device_name(0),
        "pt": str(pt_path),
        "engine": str(engine_path) if engine_path and engine_path.is_file() else "",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
