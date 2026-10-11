"""Run feature package.

Import the aggregate mixin from here; use individual modules for task-local edits.
"""

from .audio import AudioRunMixin
from .video import VideoRunMixin
from .lifecycle import RunLifecycleMixin


class RunMixin(AudioRunMixin, VideoRunMixin, RunLifecycleMixin):
    """Composition-only aggregate; contains no feature behavior itself."""

    pass


__all__ = ["RunMixin"]
