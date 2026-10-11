"""Runtime/build identity, tool versions and log storage metrics.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import sys
import re
import threading
import subprocess
import time
import logging
import platform
import hashlib
import gzip
import uuid
from collections import Counter
from datetime import datetime, timedelta
import json
import shutil
from shutil import which


class RuntimeContextMixin:
    def get_tool_version(self, executable):
        """Читает только первую строку версии без создания отдельного process-log."""
        if not executable:
            return ""
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = subprocess.run(
                [executable, "-version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=flags,
                timeout=5,
                check=False,
            )
            first_line = result.stdout.decode("utf-8", errors="replace").splitlines()
            return first_line[0][:300] if first_line else ""
        except Exception as e:
            return f"{type(e).__name__}: {e}"

    def get_source_identity(self):
        """Хэширует весь модульный source tree, чтобы build_id менялся вместе с кодом."""
        if getattr(sys, "frozen", False):
            source_path = os.path.abspath(sys.executable)
            source_sha256 = self.sha256_file(source_path)
            try:
                return {
                    "path": source_path,
                    "source_kind": "frozen_executable",
                    "file_count": 1,
                    "files": [os.path.basename(source_path)],
                    "size_bytes": os.path.getsize(source_path),
                    "modified_at": datetime.fromtimestamp(
                        os.path.getmtime(source_path)
                    ).isoformat(timespec="seconds"),
                    "sha256": source_sha256,
                }
            except OSError as error:
                return {
                    "path": source_path,
                    "source_kind": "frozen_executable",
                    "sha256": source_sha256,
                    "inspection_error": f"{type(error).__name__}: {error}",
                }

        launcher = os.path.join(self.app_dir, "ZeTer Media Converter.py")
        package_dir = os.path.join(self.app_dir, "videovaudio")
        source_files = []
        if os.path.isfile(launcher):
            source_files.append(launcher)
        if os.path.isdir(package_dir):
            for current_root, dir_names, file_names in os.walk(package_dir):
                dir_names[:] = [
                    name for name in dir_names
                    if name != "__pycache__"
                ]
                for name in sorted(file_names):
                    if name.lower().endswith(".py"):
                        source_files.append(os.path.join(current_root, name))
        source_files = sorted(set(source_files))

        digest = hashlib.sha256()
        total_size = 0
        latest_mtime = 0.0
        relative_files = []
        for source_path in source_files:
            relative = os.path.relpath(source_path, self.app_dir).replace("\\", "/")
            relative_files.append(relative)
            file_hash = self.sha256_file(source_path)
            digest.update(relative.encode("utf-8", errors="replace"))
            digest.update(b"\0")
            digest.update(str(file_hash).encode("utf-8", errors="replace"))
            digest.update(b"\n")
            try:
                total_size += os.path.getsize(source_path)
                latest_mtime = max(latest_mtime, os.path.getmtime(source_path))
            except OSError:
                pass

        source_sha256 = digest.hexdigest() if source_files else ""
        return {
            "path": launcher,
            "source_kind": "modular_python_tree",
            "file_count": len(relative_files),
            "files": relative_files,
            "size_bytes": total_size,
            "modified_at": (
                datetime.fromtimestamp(latest_mtime).isoformat(timespec="seconds")
                if latest_mtime
                else None
            ),
            "sha256": source_sha256,
        }

    def get_runtime_context(self):
        ffmpeg_path = which("ffmpeg")
        ffprobe_path = which("ffprobe")
        source_info = self.get_source_identity()
        source_sha256 = str(source_info.get("sha256") or "")
        short_hash = (
            source_sha256[:12]
            if re.fullmatch(r"[0-9a-f]{64}", source_sha256)
            else "hash-unavailable"
        )
        self.build_id = f"{self.APP_VERSION}+sha256.{short_hash}"
        return {
            "app_version": self.APP_VERSION,
            "build_id": self.build_id,
            "diagnostic_schema_version": self.LOG_SCHEMA_VERSION,
            "platform": platform.platform(),
            "python_version": sys.version.replace("\n", " "),
            "python_executable": sys.executable,
            "frozen_exe": bool(getattr(sys, "frozen", False)),
            "cwd": os.getcwd(),
            "app_dir": self.app_dir,
            "program_file": source_info,
            "ffmpeg_path": ffmpeg_path,
            "ffmpeg_version": self.get_tool_version(ffmpeg_path),
            "ffprobe_path": ffprobe_path,
            "ffprobe_version": self.get_tool_version(ffprobe_path),
            "settings": {
                "bitrate": self.bitrate,
                "output_sample_rate_hz": self.OUTPUT_SAMPLE_RATE_HZ,
                "output_channels": self.OUTPUT_CHANNELS,
                "output_channel_layout": self.OUTPUT_CHANNEL_LAYOUT,
                "max_workers": self.max_workers,
                "split_hours": self.SPLIT_HOURS,
                "problem_log_retention_days": self.PROBLEM_LOG_RETENTION_DAYS,
                "max_retained_process_log_bytes": self.MAX_PROCESS_LOG_BYTES,
                "max_detailed_events_per_signature": self.MAX_DETAILED_EVENTS_PER_SIGNATURE,
                "max_expected_skip_details_per_signature": self.MAX_EXPECTED_SKIP_DETAILS_PER_SIGNATURE,
                "max_reproduction_argv_items": self.MAX_REPRODUCTION_ARGV_ITEMS,
                "diagnostic_files_are_per_run": True,
                "heartbeat_interval_seconds": self.HEARTBEAT_INTERVAL_SECONDS,
                "compress_detailed_logs_after_days": self.COMPRESS_DETAILED_LOGS_AFTER_DAYS,
                "concat_duration_tolerance_seconds": self.CONCAT_DURATION_TOLERANCE_SECONDS,
                "concat_duration_tolerance_max_seconds": self.CONCAT_DURATION_TOLERANCE_MAX_SECONDS,
                "mp3_frame_samples": self.MP3_FRAME_SAMPLES,
                "split_boundary_margin_frames": self.SPLIT_BOUNDARY_MARGIN_FRAMES,
                "split_max_overage_seconds": self.SPLIT_MAX_OVERAGE_SECONDS,
            },
        }

    def get_log_storage_stats(self):
        stats = {"file_count": 0, "total_bytes": 0, "by_type": {}}
        if not os.path.isdir(self.log_dir):
            return stats
        for current_root, _, files in os.walk(self.log_dir):
            for name in files:
                path = os.path.join(current_root, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if name.startswith("problems_"):
                    category = "problems_jsonl"
                elif name.startswith("summary_"):
                    category = "summary_json"
                elif name.startswith("report_"):
                    category = "report_markdown"
                elif name == "health_history.jsonl":
                    category = "health_history"
                elif name in {
                    "latest_run.json",
                    "latest_completed_run.json",
                    "current_session.json",
                    "latest_problem_summary.md",
                    "active_run_state.json",
                    "README_FOR_CODEX.md",
                }:
                    category = "diagnostic_indexes"
                elif name.startswith("conversion_"):
                    category = (
                        "conversion_log_compressed"
                        if name.lower().endswith(".gz")
                        else "conversion_log"
                    )
                elif name.startswith("crash_"):
                    category = "crash_log"
                elif name.startswith("concat_manifest_"):
                    category = "concat_manifests"
                elif current_root == self.process_output_dir:
                    category = (
                        "retained_process_failures_compressed"
                        if name.lower().endswith(".gz")
                        else "retained_process_failures"
                    )
                else:
                    category = "other"
                bucket = stats["by_type"].setdefault(category, {"files": 0, "bytes": 0})
                bucket["files"] += 1
                bucket["bytes"] += size
                stats["file_count"] += 1
                stats["total_bytes"] += size
        return stats
