"""Core feature package.

Import the aggregate mixin from here; use individual modules for task-local edits.
"""

from .paths import PathUtilsMixin
from .ffmpeg import FFmpegUtilsMixin
from .audio_contract import AudioContractMixin


class CoreMixin(PathUtilsMixin, FFmpegUtilsMixin, AudioContractMixin):
    """Composition-only aggregate; contains no feature behavior itself."""

    pass


__all__ = ["CoreMixin"]
