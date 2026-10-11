"""Storage feature package.

Import the aggregate mixin from here; use individual modules for task-local edits.
"""

from .atomic import AtomicStorageMixin
from .maintenance import LogMaintenanceMixin
from .runtime import RuntimeContextMixin
from .logging_setup import LoggingSetupMixin
from .media_scan import MediaScanMixin


class StorageMixin(AtomicStorageMixin, LogMaintenanceMixin, RuntimeContextMixin, LoggingSetupMixin, MediaScanMixin):
    """Composition-only aggregate; contains no feature behavior itself."""

    pass


__all__ = ["StorageMixin"]
