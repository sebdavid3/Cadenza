"""Etapa de preprocesado configurable de imágenes para OMR (Fase 7, Issue #15, deuda D2).

Proporciona transformaciones canónicas previas a la inferencia OMR:
1. Enderezado (deskew): maximización de varianza del perfil de proyección horizontal
   de pentagramas para corregir inclinaciones.
2. Binarización: separación óptima de tinta y fondo mediante umbralización Otsu,
   adaptativa o fija.
3. Control de resolución (rescaling / DPI): normalización de dimensiones y densidad
   de píxeles para asegurar detección adecuada de pentagramas finos.

Cada etapa es configurable e independientemente activable según ADR-0001 y ARCHITECTURE.md §5.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


@dataclass(frozen=True, slots=True)
class PreprocessingConfig:
    """Configuración inmutable de la etapa de preprocesado de imagen OMR."""

    enabled: bool = False
    deskew: bool = False
    max_deskew_angle: float = 15.0
    deskew_angle_step: float = 0.5
    deskew_refine_step: float = 0.1
    min_deskew_angle: float = 0.2
    binarize: bool = False
    binarization_method: str = "otsu"  # "otsu" | "adaptive" | "fixed"
    binarization_threshold: int = 128
    rescale: bool = False
    target_dpi: int = 300
    default_dpi: int = 72
    scale_factor: float | None = None
    min_height: int | None = None

    def to_primitive(self) -> dict[str, Any]:
        """Serializa la configuración a un diccionario primitivo."""
        return asdict(self)

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> PreprocessingConfig:
        """Construye la configuración a partir de un diccionario primitivo."""
        return cls(
            enabled=bool(data.get("enabled", False)),
            deskew=bool(data.get("deskew", False)),
            max_deskew_angle=float(data.get("max_deskew_angle", 15.0)),
            deskew_angle_step=float(data.get("deskew_angle_step", 0.5)),
            deskew_refine_step=float(data.get("deskew_refine_step", 0.1)),
            min_deskew_angle=float(data.get("min_deskew_angle", 0.2)),
            binarize=bool(data.get("binarize", False)),
            binarization_method=str(data.get("binarization_method", "otsu")),
            binarization_threshold=int(data.get("binarization_threshold", 128)),
            rescale=bool(data.get("rescale", False)),
            target_dpi=int(data.get("target_dpi", 300)),
            default_dpi=int(data.get("default_dpi", 72)),
            scale_factor=(
                None if data.get("scale_factor") is None else float(data["scale_factor"])
            ),
            min_height=(None if data.get("min_height") is None else int(data["min_height"])),
        )


def compute_deskew_angle(
    image: Image.Image,
    max_angle: float = 15.0,
    coarse_step: float = 0.5,
    refine_step: float = 0.1,
) -> float:
    """Calcula el ángulo de inclinación de la partitura mediante perfiles de proyección.

    En partituras musicales, las líneas del pentagrama generan picos pronunciados
    en la proyección horizontal cuando la imagen está perfectamente nivelada (0°).
    La varianza del perfil alcanza su máximo global exactamente en la orientación horizontal.
    """
    gray = image.convert("L")

    # Muestreo optimizado para imágenes de gran tamaño (acelera el cálculo en órdenes de magnitud)
    target_width = 800
    if gray.width > target_width:
        scale = target_width / gray.width
        new_h = max(10, round(gray.height * scale))
        gray = gray.resize((target_width, new_h), resample=Image.Resampling.BILINEAR)

    # Invertir para que la tinta (líneas oscuras) sea valor alto en la suma
    arr_inv = 255 - np.asarray(gray, dtype=np.float32)

    # 1. Búsqueda gruesa
    coarse_angles = np.arange(-max_angle, max_angle + coarse_step * 0.5, coarse_step)
    best_coarse_angle = 0.0
    max_variance = -1.0

    for ang in coarse_angles:
        # Rotar alrededor del centro
        rotated = Image.fromarray(arr_inv).rotate(
            float(-ang), resample=Image.Resampling.NEAREST, fillcolor=0
        )
        rot_arr = np.asarray(rotated)
        profile = rot_arr.sum(axis=1)
        var = float(np.var(profile))
        if var > max_variance:
            max_variance = var
            best_coarse_angle = float(ang)

    # 2. Refinamiento fino alrededor del mejor ángulo grueso
    search_min = max(-max_angle, best_coarse_angle - coarse_step)
    search_max = min(max_angle, best_coarse_angle + coarse_step)
    fine_angles = np.arange(search_min, search_max + refine_step * 0.5, refine_step)

    best_angle = best_coarse_angle
    for ang in fine_angles:
        rotated = Image.fromarray(arr_inv).rotate(
            float(-ang), resample=Image.Resampling.BILINEAR, fillcolor=0
        )
        rot_arr = np.asarray(rotated)
        profile = rot_arr.sum(axis=1)
        var = float(np.var(profile))
        if var > max_variance:
            max_variance = var
            best_angle = float(ang)

    return round(best_angle, 2)


def deskew_image(
    image: Image.Image,
    angle: float,
    min_angle: float = 0.2,
) -> tuple[Image.Image, float]:
    """Endereza una imagen rotándola por el ángulo detectado si supera el umbral mínimo."""
    if abs(angle) < min_angle:
        return image, 0.0

    # Rellenar con blanco el fondo rotado
    fill_color = 255 if image.mode in ("L", "1") else (255, 255, 255)
    deskewed = image.rotate(
        -angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=fill_color,
    )
    return deskewed, angle


def compute_otsu_threshold(image: Image.Image) -> int:
    """Calcula el umbral óptimo global de Otsu maximizando la varianza inter-clase."""
    gray = image.convert("L")
    arr = np.asarray(gray)
    hist, _ = np.histogram(arr.ravel(), bins=256, range=(0, 256))
    total = arr.size
    if total == 0:
        return 128

    sum_total = float(np.dot(np.arange(256), hist))
    weight_background = 0
    sum_background = 0.0
    max_variance = -1.0
    t_start = 128
    t_end = 128

    for t in range(256):
        weight_background += hist[t]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break

        sum_background += float(t * hist[t])
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground

        variance = (
            float(weight_background)
            * float(weight_foreground)
            * ((mean_background - mean_foreground) ** 2)
        )

        if variance > max_variance + 1e-6:
            max_variance = variance
            t_start = t
            t_end = t
        elif abs(variance - max_variance) <= 1e-6:
            t_end = t

    return (t_start + t_end) // 2


def binarize_image(
    image: Image.Image,
    method: str = "otsu",
    threshold: int = 128,
) -> Image.Image:
    """Binariza una imagen produciendo fondo blanco (255) y tinta negra (0)."""
    gray = image.convert("L")
    arr = np.asarray(gray)

    if method == "otsu":
        thresh = compute_otsu_threshold(gray)
    elif method == "fixed":
        thresh = threshold
    elif method == "adaptive":
        # Umbralización adaptativa local con media por bloques
        block_size = max(11, (min(gray.width, gray.height) // 20) | 1)
        # Aproximación eficiente de fondo con blur/filtro de caja
        from PIL import ImageFilter

        blurred = gray.filter(ImageFilter.BoxBlur(block_size // 2))
        thresh_arr = np.asarray(blurred) - 10
        binary_arr = np.where(arr > thresh_arr, 255, 0).astype(np.uint8)
        return Image.fromarray(binary_arr, mode="L")
    else:
        thresh = threshold

    binary_arr = np.where(arr > thresh, 255, 0).astype(np.uint8)
    return Image.fromarray(binary_arr, mode="L")


def rescale_image(
    image: Image.Image,
    target_dpi: int = 300,
    default_dpi: int = 72,
    scale_factor: float | None = None,
    min_height: int | None = None,
) -> tuple[Image.Image, float]:
    """Escala la imagen controlando resolución (DPI), dimensiones mínimas o factor explícito."""
    if scale_factor is not None and scale_factor > 0:
        factor = float(scale_factor)
    elif min_height is not None and image.height < min_height:
        factor = float(min_height) / float(image.height)
    else:
        # Sondeo de DPI en los metadatos de la imagen
        dpi_info = image.info.get("dpi")
        current_dpi: float = float(default_dpi)
        if isinstance(dpi_info, (tuple, list)) and len(dpi_info) >= 2 and dpi_info[0] > 0:
            current_dpi = float(dpi_info[0])

        factor = float(target_dpi) / current_dpi if current_dpi > 0 else 1.0

    if abs(factor - 1.0) < 0.01:
        return image, 1.0

    new_width = max(1, round(image.width * factor))
    new_height = max(1, round(image.height * factor))

    rescaled = image.resize((new_width, new_height), resample=Image.Resampling.LANCZOS)
    rescaled.info["dpi"] = (target_dpi, target_dpi)
    return rescaled, round(factor, 4)


def preprocess_image(
    image: Image.Image,
    config: PreprocessingConfig,
) -> tuple[Image.Image, dict[str, Any]]:
    """Ejecuta el pipeline completo de preprocesado según la configuración provista.

    El orden canónico de aplicación es:
    1. Rescale (control de resolución y normalización de densidad previa)
    2. Deskew (alineación ortogonal de pentagramas)
    3. Binarize (segmentación óptima de tinta y fondo)
    """
    if not config.enabled:
        return image, {"applied": False, "config": config.to_primitive()}

    current = image
    metadata: dict[str, Any] = {
        "applied": True,
        "config": config.to_primitive(),
        "original_size": list(image.size),
        "original_mode": image.mode,
    }

    # 1. Rescale / DPI
    if config.rescale:
        current, factor = rescale_image(
            current,
            target_dpi=config.target_dpi,
            default_dpi=config.default_dpi,
            scale_factor=config.scale_factor,
            min_height=config.min_height,
        )
        metadata["rescale"] = {
            "applied": abs(factor - 1.0) >= 0.01,
            "scale_factor": factor,
            "target_dpi": config.target_dpi,
            "new_size": list(current.size),
        }

    # 2. Deskew / Enderezado
    if config.deskew:
        angle = compute_deskew_angle(
            current,
            max_angle=config.max_deskew_angle,
            coarse_step=config.deskew_angle_step,
            refine_step=config.deskew_refine_step,
        )
        current, applied_angle = deskew_image(
            current,
            angle,
            min_angle=config.min_deskew_angle,
        )
        metadata["deskew"] = {
            "applied": applied_angle != 0.0,
            "detected_angle": angle,
            "applied_angle": applied_angle,
        }

    # 3. Binarize / Binarización
    if config.binarize:
        effective_thresh = (
            compute_otsu_threshold(current)
            if config.binarization_method == "otsu"
            else config.binarization_threshold
        )
        current = binarize_image(
            current,
            method=config.binarization_method,
            threshold=effective_thresh,
        )
        metadata["binarize"] = {
            "applied": True,
            "method": config.binarization_method,
            "threshold": effective_thresh,
        }

    metadata["final_size"] = list(current.size)
    metadata["final_mode"] = current.mode
    return current, metadata


def preprocess_image_file(
    input_path: Path,
    output_path: Path,
    config: PreprocessingConfig,
) -> dict[str, Any]:
    """Carga una imagen de disco, aplica el preprocesado y guarda el resultado."""
    if not input_path.is_file():
        raise FileNotFoundError(f"image not found: {input_path}")

    with Image.open(input_path) as img:
        processed_img, metadata = preprocess_image(img, config)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Guardar conservando formato PNG para evitar artefactos de compresión con pérdidas
        processed_img.save(output_path, format="PNG")

    return metadata
