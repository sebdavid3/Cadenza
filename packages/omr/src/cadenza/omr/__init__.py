"""Adaptador OMR de Cadenza: puerto `OMREngine` y adaptadores concretos."""

from __future__ import annotations

from .adapters import FakeOMREngine, HOMREngine
from .adapters.homr import ensure_cuda_dll_dirs
from .engine import OMREngine
from .errors import OMRError, OMRTranscriptionError
from .preprocessing import (
    PreprocessingConfig,
    binarize_image,
    compute_deskew_angle,
    compute_otsu_threshold,
    deskew_image,
    preprocess_image,
    preprocess_image_file,
    rescale_image,
)

__all__ = [
    "FakeOMREngine",
    "HOMREngine",
    "OMREngine",
    "OMRError",
    "OMRTranscriptionError",
    "PreprocessingConfig",
    "binarize_image",
    "compute_deskew_angle",
    "compute_otsu_threshold",
    "deskew_image",
    "ensure_cuda_dll_dirs",
    "preprocess_image",
    "preprocess_image_file",
    "rescale_image",
]
