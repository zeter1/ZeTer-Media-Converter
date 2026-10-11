"""Video feature package.

Import the aggregate mixin from here; use individual modules for task-local edits.
"""

from .profile import VideoProfileMixin
from .operations import VideoOperationsMixin
from .folder_workflow import VideoFolderWorkflowMixin


class VideoMixin(VideoProfileMixin, VideoOperationsMixin, VideoFolderWorkflowMixin):
    """Composition-only aggregate; contains no feature behavior itself."""

    pass


__all__ = ["VideoMixin"]
