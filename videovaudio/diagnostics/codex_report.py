"""Codex-focused prioritization and improvement report.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta
import json


class CodexReportMixin:
    def diagnostic_status_counts(self):
        """Считает восстановленные, ожидаемые и нерешённые события."""
        counts = Counter(
            status
            for event_id, status in self.event_status.items()
            if self.event_records.get(event_id, {}).get("kind")
            not in {"recovery_succeeded", "recovery_failed"}
        )
        return {
            "recovered": counts.get("recovered", 0),
            "expected_skip": counts.get("expected_skip", 0),
            "retrying": counts.get("retrying", 0),
            "unresolved": counts.get("unresolved", 0),
        }

    def compact_event_for_report(self, event_id):
        """Оставляет в Codex-отчёте только поля, нужные для приоритизации."""
        record = self.event_records.get(event_id, {})
        return {
            "event_id": event_id,
            "kind": record.get("kind"),
            "severity": record.get("severity"),
            "resolution_status": self.event_status.get(
                event_id,
                record.get("resolution_status"),
            ),
            "error_signature": record.get("error_signature"),
            "message": record.get("message"),
            "file": record.get("file"),
            "folder": record.get("folder"),
            "diagnosis_code": (
                record.get("diagnosis", {}).get("code")
                if isinstance(record.get("diagnosis"), dict)
                else None
            ),
            "likely_cause": (
                record.get("codex", {}).get("likely_cause")
                if isinstance(record.get("codex"), dict)
                else None
            ),
            "codex_action": (
                record.get("codex", {}).get("codex_action")
                if isinstance(record.get("codex"), dict)
                else None
            ),
            "process_log_file": record.get("process_log_file"),
        }

    def build_codex_report(self, summary):
        """Формирует конкретный порядок анализа, а не общий список советов."""
        unresolved_ids = [
            event_id
            for event_id, status in self.event_status.items()
            if status == "unresolved"
            and self.event_records.get(event_id, {}).get("kind")
            not in {"recovery_failed"}
        ]
        recovered_ids = [
            event_id
            for event_id, status in self.event_status.items()
            if status == "recovered"
            and self.event_records.get(event_id, {}).get("kind")
            not in {"recovery_succeeded"}
        ]
        expected_skip_ids = [
            event_id
            for event_id, status in self.event_status.items()
            if status == "expected_skip"
        ]

        opportunities = []
        folders = summary.get("folders") if isinstance(summary.get("folders"), list) else []
        current_elapsed = float(summary.get("elapsed_seconds", 0) or 0)
        stage_totals = Counter()
        for folder in folders:
            metrics = folder.get("stage_metrics")
            if not isinstance(metrics, dict):
                continue
            for key, value in metrics.items():
                if (
                    key.endswith("_seconds")
                    and key != "folder_wall_seconds"
                    and isinstance(value, (int, float))
                ):
                    stage_totals[key] += value
        if stage_totals:
            slowest_stage, slowest_seconds = stage_totals.most_common(1)[0]
            total_worker_seconds = sum(
                float(
                    (folder.get("conversion_metrics") or {}).get(
                        "total_elapsed_worker_seconds",
                        0,
                    )
                    or 0
                )
                for folder in folders
            )
            conversion_wall_seconds = float(
                stage_totals.get("conversion_wall_seconds", 0) or 0
            )
            worker_pool_utilization_percent = (
                total_worker_seconds
                / (conversion_wall_seconds * self.max_workers)
                * 100
                if conversion_wall_seconds > 0 and self.max_workers > 0
                else None
            )
            stage_actions = {
                "conversion_wall_seconds": (
                    "Сравнить загрузку CPU, памяти, диска и занятость пула; "
                    "менять число потоков только после этого."
                ),
                "concat_copy_seconds": (
                    "Проверить скорость диска и размер полного MP3."
                ),
                "concat_fallback_seconds": (
                    "Изучить причины fallback и аудиопрофили входов."
                ),
                "concat_duration_repair_seconds": (
                    "Проверить временные метки и накопленный MP3 padding."
                ),
                "split_seconds": (
                    "Сравнить copy и transcode-части, их число и скорость диска."
                ),
                "scan_seconds": (
                    "Проверить число файлов, глубину и недоступные каталоги."
                ),
                "cleanup_seconds": (
                    "Проверить количество временных файлов и блокировки."
                ),
            }
            opportunities.append({
                "kind": "largest_actionable_stage_cost",
                "stage": slowest_stage,
                "total_seconds": slowest_seconds,
                "percent_of_run": (
                    slowest_seconds / current_elapsed * 100
                    if current_elapsed > 0
                    else None
                ),
                "stage_breakdown": [
                    {
                        "stage": stage,
                        "total_seconds": seconds,
                        "percent_of_run": (
                            seconds / current_elapsed * 100
                            if current_elapsed > 0
                            else None
                        ),
                    }
                    for stage, seconds in stage_totals.most_common()
                ],
                "configured_max_workers": self.max_workers,
                "worker_pool_utilization_percent": (
                    worker_pool_utilization_percent
                ),
                "resource_metrics": summary.get("resource_metrics", {}),
                "codex_action": stage_actions.get(
                    slowest_stage,
                    "Проверить самый дорогой реальный этап без потери качества.",
                ),
            })

        fallback_count = sum(
            count
            for kind, count in self.problem_counts.items()
            if "retry" in kind or "fallback" in kind
        )
        if fallback_count:
            opportunities.append({
                "kind": "recovery_overhead",
                "event_count": fallback_count,
                "codex_action": "Искать первопричину повторных попыток и устранять её до дорогого fallback.",
            })

        recent = self.read_recent_health_records(limit=10)
        current_input_files = sum(
            int(folder.get("input_files", 0) or 0)
            for folder in folders
        )
        current_audio_seconds = sum(
            float(folder.get("original_duration_seconds", 0) or 0)
            for folder in folders
        )
        comparable = [
            float(item.get("elapsed_seconds", 0) or 0)
            for item in recent
            if int(item.get("input_files", 0) or 0)
            == current_input_files
            and (
                current_audio_seconds <= 0
                or abs(
                    float(item.get("audio_duration_seconds", 0) or 0)
                    - current_audio_seconds
                )
                <= max(10.0, current_audio_seconds * 0.10)
            )
            and float(item.get("elapsed_seconds", 0) or 0) > 0
        ]
        regressions = []
        if comparable:
            baseline = sum(comparable) / len(comparable)
            if baseline > 0 and current_elapsed > baseline * 1.25:
                regressions.append({
                    "metric": "elapsed_seconds",
                    "current": current_elapsed,
                    "baseline_average": baseline,
                    "change_percent": (
                        (current_elapsed - baseline) / baseline * 100
                    ),
                })

        def group_by_signature(event_ids):
            grouped = {}
            for event_id in event_ids:
                item = self.compact_event_for_report(event_id)
                signature = item.get("error_signature") or event_id
                if signature in grouped:
                    continue
                signature_stats = self.problem_signature_stats.get(
                    signature,
                    {},
                )
                item.update({
                    "occurrences": signature_stats.get("count", 1),
                    "suppressed_occurrences": signature_stats.get(
                        "suppressed_count",
                        0,
                    ),
                    "sample_event_ids": signature_stats.get(
                        "sample_event_ids",
                        [event_id],
                    ),
                    "sample_files": signature_stats.get(
                        "sample_files",
                        [],
                    ),
                })
                grouped[signature] = item
            return list(grouped.values())

        review_order = sorted(
            group_by_signature(unresolved_ids),
            key=lambda item: (
                {"critical": 0, "error": 1, "warning": 2}.get(
                    item.get("severity"),
                    3,
                ),
                item.get("kind") or "",
            ),
        )
        diagnostic_health = (
            summary.get("diagnostic_health")
            if isinstance(summary.get("diagnostic_health"), dict)
            else self.diagnostic_health_snapshot()
        )
        if diagnostic_health.get("diagnostics_degraded"):
            failure_kinds = [
                item.get("kind")
                for item in diagnostic_health.get("failures", [])
                if item.get("kind")
            ]
            review_order.insert(0, {
                "event_id": None,
                "kind": "internal_diagnostics_degraded",
                "severity": "warning",
                "resolution_status": "unresolved",
                "message": (
                    "Служебные файлы диагностики записывались с ошибками; "
                    "результат конвертации нужно оценивать отдельно."
                ),
                "likely_cause": (
                    ", ".join(failure_kinds)
                    or "Остались временные файлы атомарной записи."
                ),
                "codex_action": (
                    "Проверить diagnostic_health, обычный лог и доступ к "
                    "служебным файлам."
                ),
                "occurrences": int(
                    diagnostic_health.get("failure_count", 0) or 0
                ),
                "sample_files": diagnostic_health.get(
                    "active_state_temp_files",
                    [],
                ),
            })
        return {
            "confirmed_bugs": review_order,
            "recovered_problems": group_by_signature(recovered_ids),
            "expected_skips": group_by_signature(expected_skip_ids)[:20],
            "expected_skip_count": len(expected_skip_ids),
            "performance_regressions": regressions,
            "improvement_opportunities": opportunities,
            "recommended_review_order": review_order,
            "summary": (
                "Сначала проверить confirmed_bugs; recovered_problems уже исправлены "
                "внутри текущего запуска, expected_skips не являются падением программы."
            ),
        }
