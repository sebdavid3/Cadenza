"""Mapa determinista tiempo→ancla para reproducción sincronizada (#42, D12).

Calcula de forma pura, exacta y determinista el instante de inicio global
(`offset_beats`) y duración (`duration_beats`) en pulsos de negra (quarter-note beats)
para cada evento musical del `ScoreIR`, resolviendo voces simultáneas, acordes,
silencios y cambios de métrica a lo largo de los compases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .anchor import Anchor, EventKind
from .score import ScoreIR
from .time_signature import TimeSignature


@dataclass(frozen=True, slots=True)
class EventTiming:
    """Instante y duración de un evento musical en pulsos (quarter-note beats)."""

    anchor: Anchor
    kind: EventKind
    measure_number: int
    voice: int
    offset_beats: Fraction
    duration_beats: Fraction
    measure_offset_beats: Fraction

    def offset_seconds(self, bpm: float = 120.0) -> float:
        """Calcula el instante global de inicio en segundos dado un tempo en BPM."""
        if bpm <= 0:
            raise ValueError("BPM must be positive")
        return float(self.offset_beats * 60 / Fraction(str(bpm)))

    def duration_seconds(self, bpm: float = 120.0) -> float:
        """Calcula la duración en segundos dado un tempo en BPM."""
        if bpm <= 0:
            raise ValueError("BPM must be positive")
        return float(self.duration_beats * 60 / Fraction(str(bpm)))

    def to_primitive(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_primitive(),
            "kind": self.kind.value,
            "measure_number": self.measure_number,
            "voice": self.voice,
            "offset_beats": str(self.offset_beats),
            "duration_beats": str(self.duration_beats),
            "measure_offset_beats": str(self.measure_offset_beats),
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> EventTiming:
        return cls(
            anchor=Anchor.from_primitive(data["anchor"]),
            kind=EventKind(str(data["kind"])),
            measure_number=int(data["measure_number"]),
            voice=int(data["voice"]),
            offset_beats=Fraction(str(data["offset_beats"])),
            duration_beats=Fraction(str(data["duration_beats"])),
            measure_offset_beats=Fraction(str(data["measure_offset_beats"])),
        )


@dataclass(frozen=True, slots=True)
class TimingMap:
    """Mapa ordenado de tiempos por ancla para alimentar el cursor y Tone.js."""

    events: tuple[EventTiming, ...]
    total_beats: Fraction
    measure_offsets: Mapping[int, Fraction]

    def total_seconds(self, bpm: float = 120.0) -> float:
        """Calcula la duración total de la obra en segundos dado un tempo en BPM."""
        if bpm <= 0:
            raise ValueError("BPM must be positive")
        return float(self.total_beats * 60 / Fraction(str(bpm)))

    def get(self, anchor: Anchor) -> EventTiming | None:
        """Busca el tiempo de un ancla específica por identidad o clave lógica canónica."""
        target_key = anchor.sort_key()
        for ev in self.events:
            if ev.anchor == anchor or ev.anchor.sort_key() == target_key:
                return ev
        return None

    def sounding_events(self) -> tuple[EventTiming, ...]:
        """Filtra únicamente los eventos audibles (notas con duración > 0)."""
        return tuple(
            ev for ev in self.events if ev.kind == EventKind.NOTE and ev.duration_beats > 0
        )

    def to_primitive(self) -> dict[str, Any]:
        return {
            "events": [ev.to_primitive() for ev in self.events],
            "total_beats": str(self.total_beats),
            "measure_offsets": {str(k): str(v) for k, v in self.measure_offsets.items()},
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> TimingMap:
        events = tuple(EventTiming.from_primitive(ev) for ev in data["events"])
        total_beats = Fraction(str(data["total_beats"]))
        offsets = {int(k): Fraction(str(v)) for k, v in data.get("measure_offsets", {}).items()}
        return cls(events=events, total_beats=total_beats, measure_offsets=offsets)


def compute_timing_map(score: ScoreIR) -> TimingMap:
    """Calcula el mapa tiempo→ancla determinista a partir del `ScoreIR` (#42, D12).

    Reglas puras del cálculo:
    1. Identifica el orden global de compases a través de todas las partes y pentagramas.
    2. Rastrea la signatura de compás activa; si un compás no declara métrica explícita,
       hereda la del compás precedente (por defecto 4/4 si el inicio carece de ella).
    3. La duración nominal de cada compás en pulsos se deriva de su métrica (`quarter_length`).
       Si las voces de un compás superan dicha duración, se expande al máximo de voz observado.
    4. El instante de inicio de cada compás (`measure_offsets[m]`) es la suma acumulada de
       las duraciones de los compases precedentes.
    5. Dentro de cada voz en un compás, los eventos acumulan duración de forma secuencial.
       Los eventos con `is_chord=True` comparten el instante de inicio de la nota anterior.
    6. Eventos no acústicos (claves, armaduras, signaturas) tienen duración 0 y se anclan
       en el instante actual de la voz.
    """
    if not score.parts:
        return TimingMap(events=(), total_beats=Fraction(0), measure_offsets={})

    # 1. Determinar todos los compases presentes en orden numérico
    measure_numbers: list[int] = []
    seen_measures: set[int] = set()
    for part in score.parts:
        for staff in part.staves:
            for m in staff.measures:
                if m.number not in seen_measures:
                    seen_measures.add(m.number)
                    measure_numbers.append(m.number)
    measure_numbers.sort()

    if not measure_numbers:
        return TimingMap(events=(), total_beats=Fraction(0), measure_offsets={})

    # 2. Calcular la signatura de compás y duración de cada número de compás
    measure_durations: dict[int, Fraction] = {}
    active_ts = TimeSignature(beats=4, beat_type=4)

    for m_num in measure_numbers:
        # Buscar si algún pentagrama declara TimeSignature en este compás
        for part in score.parts:
            for staff in part.staves:
                for m in staff.measures:
                    if m.number == m_num and m.time_signature is not None:
                        active_ts = m.time_signature
                        break

        nom_duration = active_ts.quarter_length

        # Comprobar la duración máxima real de las voces en este compás
        max_voice_len = Fraction(0)
        for part in score.parts:
            for staff in part.staves:
                for m in staff.measures:
                    if m.number == m_num:
                        voice_lens: dict[int, Fraction] = {}
                        for ev in m.events:
                            if not ev.is_chord and ev.duration_beats is not None:
                                voice_lens[ev.voice] = (
                                    voice_lens.get(ev.voice, Fraction(0)) + ev.duration_beats
                                )
                        for v_len in voice_lens.values():
                            if v_len > max_voice_len:
                                max_voice_len = v_len

        # Si el compás tiene eventos que exceden la métrica, se respeta la duración mayor
        # Si es un compás de anacrusa (al inicio sin silencios explícitos y < métrica), se ajusta
        if max_voice_len > nom_duration:
            measure_durations[m_num] = max_voice_len
        elif m_num == measure_numbers[0] and 0 < max_voice_len < nom_duration:
            # Compás 1 o 0 de anacrusa: duración exacta de los eventos
            measure_durations[m_num] = max_voice_len
        else:
            measure_durations[m_num] = nom_duration

    # 3. Derivar offsets acumulados por compás
    measure_offsets: dict[int, Fraction] = {}
    current_offset = Fraction(0)
    for m_num in measure_numbers:
        measure_offsets[m_num] = current_offset
        current_offset += measure_durations[m_num]

    total_beats = current_offset

    # 4. Derivar EventTiming para cada evento y ancla
    timing_events: list[EventTiming] = []

    for part_idx, part in enumerate(score.parts):
        for staff_idx, staff in enumerate(part.staves):
            for measure in staff.measures:
                m_start = measure_offsets.get(measure.number, Fraction(0))
                voice_offsets: dict[int, Fraction] = {}
                last_note_offsets: dict[int, Fraction] = {}
                counters: dict[int, int] = {}

                for event in measure.events:
                    v = event.voice
                    idx = counters.get(v, 0)
                    counters[v] = idx + 1

                    anchor = Anchor(
                        part=part_idx,
                        staff=staff_idx,
                        measure=measure.number,
                        voice=v,
                        event_index=idx,
                        staff_id=staff.id,
                        bbox=event.bbox,
                        confidence=event.confidence,
                    )

                    dur = event.duration_beats if event.duration_beats is not None else Fraction(0)

                    if event.is_chord:
                        # Acorde: suena en el mismo instante que la nota anterior de la voz
                        ev_m_offset = last_note_offsets.get(v, Fraction(0))
                    else:
                        ev_m_offset = voice_offsets.get(v, Fraction(0))
                        last_note_offsets[v] = ev_m_offset
                        voice_offsets[v] = ev_m_offset + dur

                    ev_global_offset = m_start + ev_m_offset

                    timing_events.append(
                        EventTiming(
                            anchor=anchor,
                            kind=event.kind,
                            measure_number=measure.number,
                            voice=v,
                            offset_beats=ev_global_offset,
                            duration_beats=dur,
                            measure_offset_beats=ev_m_offset,
                        )
                    )

    # Ordenar por offset_beats y sort_key del ancla para iteración determinista
    timing_events.sort(key=lambda t: (t.offset_beats, t.anchor.sort_key()))

    return TimingMap(
        events=tuple(timing_events),
        total_beats=total_beats,
        measure_offsets=measure_offsets,
    )
