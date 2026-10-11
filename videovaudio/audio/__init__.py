"""Audio feature package.

Import the aggregate mixin from here; use individual modules for task-local edits.
"""

from .file_conversion import AudioFileConversionMixin
from .folder_workflow import AudioFolderWorkflowMixin
from .split import AudioSplitMixin
from .probe import AudioProbeMixin


class AudioMixin(AudioFileConversionMixin, AudioFolderWorkflowMixin, AudioSplitMixin, AudioProbeMixin):
    """Composition-only aggregate; contains no feature behavior itself."""

    pass


__all__ = ["AudioMixin"]
