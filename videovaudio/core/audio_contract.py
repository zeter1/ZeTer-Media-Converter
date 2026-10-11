"""Audio invariants, duration tolerances and concat manifest helpers.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import hashlib
from datetime import datetime


class AudioContractMixin:
    def duration_mismatch(self, expected, actual):
        """Возвращает предел и величину недопустимого расхождения длительностей."""
        difference = abs(float(actual or 0) - float(expected or 0))
        proportional_tolerance = (
            float(expected or 0) * self.CONCAT_DURATION_TOLERANCE_RATIO
        )
        tolerance = min(
            self.CONCAT_DURATION_TOLERANCE_MAX_SECONDS,
            max(self.CONCAT_DURATION_TOLERANCE_SECONDS, proportional_tolerance),
        )
        return difference > tolerance, difference, tolerance

    def expected_audio_profile(self):
        """Единый профиль MP3, обязательный для безопасной concat-склейки."""
        payload = {
            "sample_rate_hz": self.OUTPUT_SAMPLE_RATE_HZ,
            "channels": self.OUTPUT_CHANNELS,
            "channel_layout": self.OUTPUT_CHANNEL_LAYOUT,
        }
        return payload

    def audio_profile_key(self, profile):
        """Компактный ключ аудиопрофиля для JSON-сводки."""
        profile = profile if isinstance(profile, dict) else {}
        sample_rate = profile.get("sample_rate_hz") or "unknown"
        channels = profile.get("channels") or "unknown"
        channel_layout = profile.get("channel_layout") or "unknown"
        return f"{sample_rate}Hz/{channels}ch/{channel_layout}"

    def audio_profile_matches_target(self, profile):
        """Проверяет важные для concat параметры фактически созданного MP3."""
        if not isinstance(profile, dict):
            return False
        return (
            profile.get("sample_rate_hz") == self.OUTPUT_SAMPLE_RATE_HZ
            and profile.get("channels") == self.OUTPUT_CHANNELS
        )

    def save_concat_input_manifest(self, folder_path, converted_results):
        """Сохраняет полный компактный порядок MP3 только при проблеме склейки."""
        cumulative = 0.0
        inputs = []
        for result in converted_results:
            duration = float(result.get("duration_seconds", 0) or 0)
            inputs.append({
                "index": int(result.get("index", 0) or 0) + 1,
                "file": result.get("path"),
                "name": result.get("name"),
                "duration_seconds": duration,
                "expected_start_seconds": cumulative,
                "expected_end_seconds": cumulative + duration,
                "audio_profile": result.get("audio_profile"),
                "output_size_bytes": result.get("output_size_bytes"),
            })
            cumulative += duration
        safe_folder = self.safe_log_fragment(
            os.path.basename(folder_path),
            fallback="folder",
            limit=60,
        )
        folder_hash = hashlib.sha256(
            os.path.normcase(os.path.abspath(folder_path)).encode(
                "utf-8",
                errors="replace",
            )
        ).hexdigest()[:10]
        manifest_path = os.path.join(
            self.process_output_dir,
            (
                f"concat_manifest_{self.session_id}_"
                f"{safe_folder}_{folder_hash}.json"
            ),
        )
        self.atomic_write_json(
            manifest_path,
            {
                "schema_version": self.LOG_SCHEMA_VERSION,
                "session_id": self.session_id,
                "folder": folder_path,
                "input_count": len(inputs),
                "expected_total_duration_seconds": cumulative,
                "inputs": inputs,
            },
        )
        return manifest_path
