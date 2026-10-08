"""Pruebas unitarias de la etapa de preprocesado de imagen OMR (Fase 7, Issue #15)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from cadenza.omr import (
    FakeOMREngine,
    HOMREngine,
    PreprocessingConfig,
    binarize_image,
    compute_deskew_angle,
    compute_otsu_threshold,
    deskew_image,
    preprocess_image,
    preprocess_image_file,
    rescale_image,
)
from PIL import Image


def _create_synthetic_staff_image(
    width: int = 400,
    height: int = 150,
    tilt_angle: float = 0.0,
    ink_value: int = 0,
    background_value: int = 255,
) -> Image.Image:
    """Genera una imagen sintética con cinco líneas horizontales de pentagrama."""
    arr: np.ndarray[Any, np.dtype[np.uint8]] = np.full(
        (height, width), background_value, dtype=np.uint8
    )
    # Cinco líneas de pentagrama separadas uniformemente
    staff_y = [40, 52, 64, 76, 88]
    for y in staff_y:
        arr[y : y + 2, 30 : width - 30] = ink_value

    img = Image.fromarray(arr, mode="L")
    if abs(tilt_angle) >= 0.01:
        img = img.rotate(
            tilt_angle,
            resample=Image.Resampling.BICUBIC,
            fillcolor=background_value,
        )
    return img


def test_preprocessing_config_roundtrip() -> None:
    config = PreprocessingConfig(
        enabled=True,
        deskew=True,
        max_deskew_angle=12.0,
        binarize=True,
        binarization_method="otsu",
        rescale=True,
        target_dpi=300,
        scale_factor=1.5,
    )
    primitive = config.to_primitive()
    assert primitive["enabled"] is True
    assert primitive["deskew"] is True
    assert primitive["scale_factor"] == 1.5

    rebuilt = PreprocessingConfig.from_primitive(primitive)
    assert rebuilt == config


def test_deskew_straight_image() -> None:
    img = _create_synthetic_staff_image(tilt_angle=0.0)
    angle = compute_deskew_angle(img)
    assert abs(angle) < 0.2

    deskewed, applied = deskew_image(img, angle, min_angle=0.2)
    assert applied == 0.0
    assert deskewed.size == img.size


def test_deskew_tilted_positive_angle() -> None:
    # Partitura inclinada +3.5 grados
    img = _create_synthetic_staff_image(tilt_angle=3.5)
    angle = compute_deskew_angle(img)
    # Debe detectar el ángulo con precisión <= 0.3 grados
    assert abs(angle - 3.5) <= 0.3

    deskewed, applied = deskew_image(img, angle)
    assert applied == angle
    assert deskewed.size == img.size


def test_deskew_tilted_negative_angle() -> None:
    # Partitura inclinada -4.0 grados
    img = _create_synthetic_staff_image(tilt_angle=-4.0)
    angle = compute_deskew_angle(img)
    assert abs(angle - (-4.0)) <= 0.3

    deskewed, applied = deskew_image(img, angle)
    assert applied == angle
    assert deskewed.size == img.size


def test_binarize_otsu() -> None:
    # Tinta grisácea (60) y fondo claro (230)
    img = _create_synthetic_staff_image(ink_value=60, background_value=230)
    threshold = compute_otsu_threshold(img)
    assert 60 < threshold < 230

    binary = binarize_image(img, method="otsu")
    arr = np.asarray(binary)
    unique_vals = set(np.unique(arr))
    # Solo valores puros 0 (tinta) y 255 (fondo)
    assert unique_vals.issubset({0, 255})
    assert 0 in unique_vals
    assert 255 in unique_vals


def test_binarize_fixed() -> None:
    arr: np.ndarray[Any, np.dtype[np.uint8]] = np.zeros((50, 50), dtype=np.uint8)
    arr[:25, :] = 100
    arr[25:, :] = 200
    img = Image.fromarray(arr, mode="L")

    binary = binarize_image(img, method="fixed", threshold=150)
    res_arr = np.asarray(binary)
    assert (res_arr[:25, :] == 0).all()
    assert (res_arr[25:, :] == 255).all()


def test_binarize_adaptive() -> None:
    img = _create_synthetic_staff_image(ink_value=50, background_value=240)
    binary = binarize_image(img, method="adaptive")
    unique_vals = set(np.unique(np.asarray(binary)))
    assert unique_vals.issubset({0, 255})


def test_rescale_dpi() -> None:
    img = _create_synthetic_staff_image(width=200, height=100)
    img.info["dpi"] = (150, 150)

    rescaled, factor = rescale_image(img, target_dpi=300)
    assert factor == pytest.approx(2.0, rel=1e-3)
    assert rescaled.width == 400
    assert rescaled.height == 200
    assert rescaled.info["dpi"] == (300, 300)


def test_rescale_scale_factor() -> None:
    img = _create_synthetic_staff_image(width=100, height=80)
    rescaled, factor = rescale_image(img, scale_factor=1.5)
    assert factor == 1.5
    assert rescaled.width == 150
    assert rescaled.height == 120


def test_rescale_min_height() -> None:
    img = _create_synthetic_staff_image(width=200, height=60)
    rescaled, factor = rescale_image(img, min_height=120)
    assert factor == pytest.approx(2.0, rel=1e-3)
    assert rescaled.height == 120
    assert rescaled.width == 400


def test_preprocess_pipeline_disabled() -> None:
    img = _create_synthetic_staff_image(tilt_angle=2.0)
    config = PreprocessingConfig(enabled=False, deskew=True)
    processed, meta = preprocess_image(img, config)
    assert meta["applied"] is False
    assert processed.size == img.size


def test_preprocess_pipeline_all_enabled() -> None:
    # Imagen inclinada, con tinta gris y tamaño reducido
    img = _create_synthetic_staff_image(
        width=200,
        height=80,
        tilt_angle=3.0,
        ink_value=60,
        background_value=220,
    )
    config = PreprocessingConfig(
        enabled=True,
        deskew=True,
        binarize=True,
        binarization_method="otsu",
        rescale=True,
        scale_factor=1.5,
    )
    processed, meta = preprocess_image(img, config)
    assert meta["applied"] is True
    assert "rescale" in meta
    assert "deskew" in meta
    assert "binarize" in meta
    assert processed.width == 300
    assert processed.height == 120
    # Modo final y valores binarizados
    unique_vals = set(np.unique(np.asarray(processed)))
    assert unique_vals.issubset({0, 255})


def test_preprocess_image_file(tmp_path: Path) -> None:
    src_path = tmp_path / "original.png"
    dst_path = tmp_path / "preprocessed.png"
    img = _create_synthetic_staff_image(tilt_angle=2.5, ink_value=50)
    img.save(src_path, format="PNG")

    config = PreprocessingConfig(enabled=True, deskew=True, binarize=True)
    meta = preprocess_image_file(src_path, dst_path, config)
    assert meta["applied"] is True
    assert dst_path.is_file()

    with Image.open(dst_path) as out_img:
        assert out_img.format == "PNG"
        assert set(np.unique(np.asarray(out_img))).issubset({0, 255})


def test_fake_omr_engine_records_preprocessing(tmp_path: Path) -> None:
    src_path = tmp_path / "sample.png"
    img = _create_synthetic_staff_image(tilt_angle=2.0)
    img.save(src_path, format="PNG")

    config = PreprocessingConfig(enabled=True, deskew=True, binarize=True)
    engine = FakeOMREngine(preprocessing=config)
    doc = engine.transcribe(src_path)

    assert doc.provenance.preprocessing is not None
    assert doc.provenance.preprocessing["applied"] is True
    assert "deskew" in doc.provenance.preprocessing
    assert "binarize" in doc.provenance.preprocessing


def test_homr_engine_preprocessing_property() -> None:
    config = PreprocessingConfig(enabled=True, deskew=True, rescale=True, target_dpi=300)
    engine = HOMREngine(use_gpu=False, preprocessing=config)
    assert engine.preprocessing is not None
    assert engine.preprocessing.enabled is True
    assert engine.preprocessing.deskew is True
    assert engine.preprocessing.target_dpi == 300
