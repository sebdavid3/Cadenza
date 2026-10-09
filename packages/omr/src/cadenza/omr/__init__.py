"""Adaptador OMR de Cadenza: puerto `OMREngine` y adaptadores concretos."""

from __future__ import annotations

from .adapters import OEMER_ENGINE_ID, FakeOMREngine, HOMREngine, OemerEngine
from .adapters.homr import ensure_cuda_dll_dirs, get_effective_device
from .adapters.oemer import ensure_oemer_checkpoints
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
    "OEMER_ENGINE_ID",
    "FakeOMREngine",
    "HOMREngine",
    "OMREngine",
    "OMRError",
    "OMRTranscriptionError",
    "OemerEngine",
    "PreprocessingConfig",
    "binarize_image",
    "compute_deskew_angle",
    "compute_otsu_threshold",
    "deskew_image",
    "ensure_cuda_dll_dirs",
    "ensure_oemer_checkpoints",
    "get_effective_device",
    "preprocess_image",
    "preprocess_image_file",
    "rescale_image",
]
