"""Adaptador OMR de Cadenza: puerto `OMREngine` y su único adaptador, HOMR (ADR-0018).

El doble de pruebas `FakeOMREngine` vive en `cadenza.omr.testing` y no se exporta aquí.
"""

from __future__ import annotations

from .adapters import HOMREngine
from .adapters.homr import ensure_cuda_dll_dirs, get_effective_device
from .engine import OMREngine
from .errors import OMRError, OMRTranscriptionError
from .power import PowerThrottlingMode, disable_power_throttling, set_power_throttling
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
    "HOMREngine",
    "OMREngine",
    "OMRError",
    "OMRTranscriptionError",
    "PowerThrottlingMode",
    "PreprocessingConfig",
    "binarize_image",
    "compute_deskew_angle",
    "compute_otsu_threshold",
    "deskew_image",
    "disable_power_throttling",
    "ensure_cuda_dll_dirs",
    "get_effective_device",
    "preprocess_image",
    "preprocess_image_file",
    "rescale_image",
    "set_power_throttling",
]
