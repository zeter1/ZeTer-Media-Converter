"""Diagnostics feature package.

Import the aggregate mixin from here; use individual modules for task-local edits.
"""

from .common import DiagnosticsCommonMixin
from .resources import DiagnosticsResourcesMixin
from .io_health import DiagnosticsIOHealthMixin
from .lifecycle import DiagnosticsLifecycleMixin
from .events import ProblemEventsMixin
from .codex_report import CodexReportMixin
from .integrity import DiagnosticsIntegrityMixin
from .health import DiagnosticsHealthHistoryMixin
from .run_reports import RunReportsMixin


class DiagnosticsMixin(DiagnosticsCommonMixin, DiagnosticsResourcesMixin, DiagnosticsIOHealthMixin, DiagnosticsLifecycleMixin, ProblemEventsMixin, CodexReportMixin, DiagnosticsIntegrityMixin, DiagnosticsHealthHistoryMixin, RunReportsMixin):
    """Composition-only aggregate; contains no feature behavior itself."""

    pass


__all__ = ["DiagnosticsMixin"]
