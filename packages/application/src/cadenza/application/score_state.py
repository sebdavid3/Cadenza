"""Estado materializado de una sesión, con caché y por etapas (#275, ADR-0037).

Lo comparten los casos de uso que leen o crean un estado (editar, deshacer, el detalle, la
exportación y los tiempos). `materialize` no cambia: sin caché, o con una entrada que falta,
el estado se reconstruye desde el log como siempre (ADR-0007), y lo que se guarda es lo mismo
que daría `materialize`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from cadenza.domain import (
    EditEvent,
    ScoreIR,
    TimingMap,
    compute_timing_map,
    materialize,
)

from .ports.score_exporter import ScoreExporter
from .ports.score_state_cache import CachedScoreState, ScoreStateCache, ScoreStateKey
from .stage_timing import timed_stage

logger = logging.getLogger("cadenza.application.score_state")


def state_key(session_id: str, edits: Sequence[EditEvent]) -> ScoreStateKey:
    """La clave del estado al que llega el log `edits` (ordenado por `seq`)."""
    if not edits:
        return ScoreStateKey(session_id=session_id, seq=0, last_edit_id=None)
    last = edits[-1]
    return ScoreStateKey(session_id=session_id, seq=last.seq, last_edit_id=last.id)


def raw_score_of(document: Any) -> ScoreIR:
    """El `ScoreIR` crudo de un documento de sesión (primitivo o ya construido)."""
    if hasattr(document, "score"):
        score = document.score
    elif isinstance(document, Mapping) and "score" in document:
        score = document["score"]
    else:
        raise ValueError("Documento de sesión sin ScoreIR válido")
    return score if isinstance(score, ScoreIR) else ScoreIR.from_primitive(score)


def load_state(
    session_id: str,
    document: Any,
    edits: Sequence[EditEvent],
    cache: ScoreStateCache | None,
) -> tuple[ScoreStateKey, CachedScoreState]:
    """El estado al que llega el log: de la caché o materializado (y entonces se guarda)."""
    key = state_key(session_id, edits)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return key, cached
    with timed_stage("materialize"):
        score = materialize(raw_score_of(document), edits)
    state = CachedScoreState(score=score)
    if cache is not None:
        cache.put(key, state)
    return key, state


def store_state(
    cache: ScoreStateCache | None, key: ScoreStateKey, state: CachedScoreState
) -> CachedScoreState:
    """Guarda el estado (si hay caché) y lo devuelve."""
    if cache is not None:
        cache.put(key, state)
    return state


def musicxml_of(
    key: ScoreStateKey,
    state: CachedScoreState,
    exporter: ScoreExporter,
    cache: ScoreStateCache | None,
) -> tuple[CachedScoreState, str]:
    """El MusicXML del estado, exportado una sola vez por estado."""
    if state.musicxml is not None:
        return state, state.musicxml
    with timed_stage("export"):
        xml = exporter.to_musicxml(state.score)
    updated = store_state(cache, key, replace(state, musicxml=xml))
    return updated, xml


def try_musicxml_of(
    key: ScoreStateKey,
    state: CachedScoreState,
    exporter: ScoreExporter,
    cache: ScoreStateCache | None,
) -> tuple[CachedScoreState, str | None]:
    """Como `musicxml_of`, pero sin el MusicXML (None) si la exportación falla.

    Tras guardar una edición, que su estado no se pueda exportar no la deshace: el cliente lo
    pide a `/export`, que da el error, como antes de #275 (ADR-0034 §4).
    """
    try:
        return musicxml_of(key, state, exporter, cache)
    # El exportador puede fallar de cualquier forma (music21): no se deja pasar a la edición.
    except Exception:
        logger.exception("score_export_failed session_id=%s seq=%s", key.session_id, key.seq)
        return state, None


def timing_of(
    key: ScoreStateKey,
    state: CachedScoreState,
    cache: ScoreStateCache | None,
) -> tuple[CachedScoreState, TimingMap]:
    """El mapa de tiempos del estado, calculado una sola vez por estado."""
    if state.timing is not None:
        return state, state.timing
    with timed_stage("timing"):
        timing = compute_timing_map(state.score)
    updated = store_state(cache, key, replace(state, timing=timing))
    return updated, timing
