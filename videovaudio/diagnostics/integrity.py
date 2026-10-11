"""Structural and semantic consistency checks for diagnostic artifacts.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta
import json


class DiagnosticsIntegrityMixin:
    def diagnostics_integrity(self, summary=None):
        """Проверяет синтаксис файлов и смысловую согласованность итогов."""
        diagnostic_health = (
            summary.get("diagnostic_health")
            if isinstance(summary, dict)
            and isinstance(summary.get("diagnostic_health"), dict)
            else self.diagnostic_health_snapshot()
        )
        result = {
            "ok": True,
            "structural_ok": True,
            "semantic_ok": True,
            "operational_ok": bool(
                diagnostic_health.get("operational_ok", True)
            ),
            "diagnostics_degraded": bool(
                diagnostic_health.get("diagnostics_degraded", False)
            ),
            "diagnostic_failure_count": int(
                diagnostic_health.get("failure_count", 0) or 0
            ),
            "active_state_temp_file_count": int(
                diagnostic_health.get("active_state_temp_file_count", 0)
                or 0
            ),
            "jsonl_valid_lines": 0,
            "jsonl_invalid_lines": 0,
            "invalid_line_numbers": [],
            "duplicate_event_ids": [],
            "missing_parent_event_ids": [],
            "missing_referenced_process_logs": [],
            "missing_referenced_manifests": [],
            "count_mismatches": [],
            "failed_folders_without_problem_event_ids": [],
            "invalid_folder_outcomes": [],
            "run_status_expected": None,
            "run_status_actual": (
                summary.get("status")
                if isinstance(summary, dict)
                else None
            ),
            "suppressed_duplicate_events": sum(
                item.get("suppressed_count", 0)
                for item in self.problem_signature_stats.values()
            ),
        }
        seen = set()
        referenced_process_logs = []
        referenced_manifests = []
        parent_event_ids = []

        def collect_references(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if (
                        key == "process_log_file"
                        and isinstance(child, str)
                        and child
                    ):
                        referenced_process_logs.append(child)
                    elif (
                        key == "concat_input_manifest"
                        and isinstance(child, str)
                        and child
                    ):
                        referenced_manifests.append(child)
                    else:
                        collect_references(child)
            elif isinstance(value, list):
                for child in value:
                    collect_references(child)

        try:
            with open(self.problem_log_file, "r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        result["jsonl_valid_lines"] += 1
                    except (TypeError, ValueError):
                        result["jsonl_invalid_lines"] += 1
                        result["invalid_line_numbers"].append(line_number)
                        continue
                    event_id = record.get("event_id")
                    if event_id in seen:
                        result["duplicate_event_ids"].append(event_id)
                    seen.add(event_id)
                    parent_event_id = record.get("parent_event_id")
                    if isinstance(parent_event_id, str) and parent_event_id:
                        parent_event_ids.append(parent_event_id)
                    collect_references(record)
        except Exception as e:
            result["read_error"] = f"{type(e).__name__}: {e}"

        known_event_ids = set(self.event_records) | seen
        result["missing_parent_event_ids"] = sorted({
            event_id
            for event_id in parent_event_ids
            if event_id not in known_event_ids
        })
        for path in referenced_process_logs:
            if not os.path.isfile(path) and not os.path.isfile(path + ".gz"):
                result["missing_referenced_process_logs"].append(path)
        for path in referenced_manifests:
            if not os.path.isfile(path):
                result["missing_referenced_manifests"].append(path)
        result["structural_ok"] = not (
            result.get("read_error")
            or result["jsonl_invalid_lines"]
            or result["duplicate_event_ids"]
            or result["missing_parent_event_ids"]
            or result["missing_referenced_process_logs"]
            or result["missing_referenced_manifests"]
        )
        if isinstance(summary, dict):
            folders = (
                summary.get("folders")
                if isinstance(summary.get("folders"), list)
                else []
            )
            outcome_counts = Counter()
            for folder in folders:
                outcome = folder.get("outcome")
                if not outcome:
                    if folder.get("success"):
                        outcome = "success"
                    elif folder.get("status") == "cancelled":
                        outcome = "cancelled"
                    elif str(folder.get("status") or "").startswith(
                        "skipped_"
                    ):
                        outcome = "skipped"
                    else:
                        outcome = "failed"
                if outcome not in {
                    "success",
                    "skipped",
                    "failed",
                    "cancelled",
                }:
                    result["invalid_folder_outcomes"].append({
                        "folder": folder.get("folder"),
                        "outcome": outcome,
                    })
                    continue
                outcome_counts[outcome] += 1
                if (
                    outcome == "failed"
                    and not folder.get("problem_event_ids")
                ):
                    result[
                        "failed_folders_without_problem_event_ids"
                    ].append({
                        "folder": folder.get("folder"),
                        "status": folder.get("status"),
                    })

            run_level_failure_count = (
                1
                if summary.get("status") == "crashed"
                and summary.get("problem_event_ids")
                else 0
            )
            expected_counts = {
                "processed_count": len(folders),
                "success_count": outcome_counts["success"],
                "skipped_folder_count": outcome_counts["skipped"],
                "failed_count": (
                    outcome_counts["failed"]
                    + run_level_failure_count
                ),
            }
            for field, expected in expected_counts.items():
                actual = int(summary.get(field, 0) or 0)
                if actual != expected:
                    result["count_mismatches"].append({
                        "field": field,
                        "expected": expected,
                        "actual": actual,
                    })

            cancelled = bool(summary.get("cancelled")) or bool(
                outcome_counts["cancelled"]
            )
            if summary.get("status") == "crashed":
                expected_status = "crashed"
            elif cancelled:
                expected_status = "cancelled"
            elif outcome_counts["failed"]:
                expected_status = "completed_with_errors"
            elif (
                outcome_counts["skipped"]
                or int(summary.get("skipped_media_count", 0) or 0)
            ):
                expected_status = "completed_with_skips"
            else:
                expected_status = "completed"
            result["run_status_expected"] = expected_status
            status_mismatch = summary.get("status") != expected_status

            failed_without_unresolved = (
                (
                    outcome_counts["failed"]
                    + run_level_failure_count
                ) > 0
                and self.diagnostic_status_counts()["unresolved"] == 0
            )
            if failed_without_unresolved:
                result["count_mismatches"].append({
                    "field": "failed_folders_vs_unresolved_problems",
                    "expected": "at_least_one_unresolved_problem",
                    "actual": 0,
                })

            result["semantic_ok"] = not (
                result["count_mismatches"]
                or result["failed_folders_without_problem_event_ids"]
                or result["invalid_folder_outcomes"]
                or status_mismatch
            )

        result["ok"] = (
            result["structural_ok"]
            and result["semantic_ok"]
            and result["operational_ok"]
        )
        return result
