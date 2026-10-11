#!/usr/bin/env python3
"""Fast architecture/static verification for ZeTer Media Converter."""
from __future__ import annotations

import compileall
import inspect
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CONVERTER_METHODS = 149
REQUIRED = [
    ROOT / "ZeTer Media Converter.py",
    ROOT / "AGENTS.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "AI_NAVIGATION.md",
    ROOT / "docs" / "CODE_MAP.json",
    ROOT / "docs" / "CODE_INDEX.md",
    ROOT / "docs" / "FLOWS.md",
    ROOT / "docs" / "VERIFICATION.md",
    ROOT / "tools" / "generate_code_index.py",
    ROOT / "tools" / "find_owner.py",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.exists()]
    if missing:
        fail("missing required files: " + ", ".join(missing))

    if not compileall.compile_dir(ROOT, quiet=1):
        fail("compileall failed")
    print("PASS compileall")

    sys.path.insert(0, str(ROOT))
    from videovaudio import VideoToAudioConverter

    methods = [
        name for name, value in inspect.getmembers(
            VideoToAudioConverter, predicate=inspect.isfunction
        )
        if not name.startswith("__")
    ]
    if len(methods) != EXPECTED_CONVERTER_METHODS:
        fail(
            f"VideoToAudioConverter method count {len(methods)} != "
            f"{EXPECTED_CONVERTER_METHODS}"
        )
    print(f"PASS converter methods: {len(methods)}")
    print(f"PASS app version: {VideoToAudioConverter.APP_VERSION}")

    check = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "generate_code_index.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if check.returncode != 0:
        print(check.stdout, end="")
        print(check.stderr, end="", file=sys.stderr)
        fail("generated code navigation artifacts are stale")
    print("PASS generated code index")

    # get_source_identity intentionally works without Tk initialization.
    instance = object.__new__(VideoToAudioConverter)
    instance.app_dir = str(ROOT)
    identity = instance.get_source_identity()
    files = set(identity.get("files") or [])
    nested_probe = "videovaudio/audio/file_conversion.py"
    if nested_probe not in files:
        fail("source identity does not include nested feature packages")
    expected_source_files = {
        "ZeTer Media Converter.py",
        *{
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "videovaudio").rglob("*.py")
            if "__pycache__" not in path.parts
        },
    }
    if files != expected_source_files:
        missing_identity = sorted(expected_source_files - files)
        extra_identity = sorted(files - expected_source_files)
        fail(
            "source identity mismatch; missing="
            f"{missing_identity} extra={extra_identity}"
        )
    print(f"PASS source identity: {len(files)} Python source files")

    print("VERIFIED: static architecture/import/navigation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
