from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the verified local DA3 + YOLO26 installation manifest")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--model-repo", required=True)
    parser.add_argument("--model-revision", required=True)
    args = parser.parse_args()

    import torch
    import ultralytics

    root = args.runtime_root.resolve()
    pt_path = root / "weights" / "YOLO26m" / "yolo26m.pt"
    engine_path = root / "weights" / "YOLO26m" / "yolo26m.engine"
    if not pt_path.is_file():
        raise FileNotFoundError(pt_path)
    engine_ready = engine_path.is_file()
    manifest = {
        "source_commit": args.source_commit,
        "model_repo": args.model_repo,
        "model_revision": args.model_revision,
        "source": str(root / "source"),
        "environment": str(root / "env"),
        "weights": str(root / "weights" / "DA3-SMALL"),
        "detector_weights": str(pt_path),
        "detector_engine": str(engine_path) if engine_ready else "",
        "detector_backend": "tensorrt-fp16" if engine_ready else "pytorch-cuda-fp16",
        "detector_image_size": 512,
        "detector_sha256": sha256(pt_path),
        "detector_engine_sha256": sha256(engine_path) if engine_ready else "",
        "ultralytics_version": ultralytics.__version__,
        "ultralytics_license": "AGPL-3.0-or-later / commercial enterprise option",
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
        "cache": str(root / "cache"),
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    output = root / "install_manifest.json"
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
