from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from inference import Da3Engine, VisionAnalyzer, Yolo26Detector


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark warmed DA3 + YOLO26 traffic analysis")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--depth-process-res", type=int, default=280)
    parser.add_argument("--detector-image-size", type=int, default=512)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    image_bytes = args.sample.read_bytes()
    detector_root = runtime_root / "weights" / "YOLO26m"
    engine_path = detector_root / "yolo26m.engine"
    detector_path = engine_path if engine_path.is_file() else detector_root / "yolo26m.pt"
    depth = Da3Engine(runtime_root / "weights" / "DA3-SMALL", process_res=args.depth_process_res)
    detector = Yolo26Detector(detector_path, image_size=args.detector_image_size)
    analyzer = VisionAnalyzer(depth, detector)

    for index in range(max(1, args.warmup)):
        analyzer.analyze_jpeg(
            image_bytes,
            frame_seq=index,
            capture_ts_ms=index * 1000,
            session_id="benchmark-warmup",
        )
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()

    latencies_ms: list[float] = []
    detection_counts: list[int] = []
    for index in range(args.runs):
        torch.cuda.synchronize()
        started = perf_counter()
        result = analyzer.analyze_jpeg(
            image_bytes,
            frame_seq=1000 + index,
            capture_ts_ms=(1000 + index) * 1000,
            session_id="benchmark-measured",
        )
        torch.cuda.synchronize()
        latencies_ms.append((perf_counter() - started) * 1000.0)
        detection_counts.append(len(result.get("detections", [])))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample": str(args.sample.resolve()),
        "runs": args.runs,
        "warmup_runs": max(1, args.warmup),
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "detector": detector.model_name,
        "detector_backend": detector.backend,
        "detector_image_size": args.detector_image_size,
        "depth": depth.model_name,
        "depth_process_res": args.depth_process_res,
        "mean_ms": round(statistics.mean(latencies_ms), 3),
        "p95_ms": round(float(np.percentile(latencies_ms, 95)), 3),
        "max_ms": round(max(latencies_ms), 3),
        "min_ms": round(min(latencies_ms), 3),
        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2),
        "detections_min": min(detection_counts),
        "detections_max": max(detection_counts),
    }
    output = args.output or runtime_root / "logs" / "traffic-benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
