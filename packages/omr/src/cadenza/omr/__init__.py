"""Adaptador OMR de Cadenza: puerto `OMREngine` y su único adaptador, HOMR (ADR-0018).

La etapa del compás (`MeterStage`, ADR-0059) corre después del motor, fuera de `HOMREngine`.

El doble de pruebas `FakeOMREngine` vive en `cadenza.omr.testing` y no se exporta aquí.
"""

from __future__ import annotations

from .adapters import HOMREngine
from .adapters.homr import ensure_cuda_dll_dirs, get_effective_device
from .engine import OMREngine
from .errors import OMRError, OMRTranscriptionError
from .meter_stage import (
    ALL_METER_FEATURES,
    METER_STAGE_VERSION,
    MeterFeature,
    MeterStage,
    MeterStageReport,
    parse_meter_features,
    recognize_meter,
)
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
    "ALL_METER_FEATURES",
    "METER_STAGE_VERSION",
    "HOMREngine",
    "MeterFeature",
    "MeterStage",
    "MeterStageReport",
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
    "parse_meter_features",
    "preprocess_image",
    "preprocess_image_file",
    "recognize_meter",
    "rescale_image",
    "set_power_throttling",
]
