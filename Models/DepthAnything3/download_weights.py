from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

from huggingface_hub import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo")
    parser.add_argument("--revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--sha256-prefix", default="")
    args = parser.parse_args()
    if args.url:
        if args.output_file is None:
            raise SystemExit("--output-file is required with --url")
        args.output_file.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(args.url) as response, args.output_file.open("wb") as target:
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        digest = hashlib.sha256(args.output_file.read_bytes()).hexdigest()
        if args.sha256_prefix and not digest.lower().startswith(args.sha256_prefix.lower()):
            args.output_file.unlink(missing_ok=True)
            raise SystemExit(f"downloaded file hash mismatch: {digest}")
        return
    if not args.repo or not args.revision or not args.output:
        raise SystemExit("--repo, --revision and --output are required for Hugging Face downloads")
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=args.repo,
        revision=args.revision,
        local_dir=args.output,
    )


if __name__ == "__main__":
    main()
