/** Estado editorial HITL (Zustand): selección, log de ediciones y undo/redo. */

import { create } from "zustand";

import type { Anchor, EditEvent, ScoreDocument, SessionDetail } from "../types";

export interface EventInfo {
  kind: string;
  pitch: string | null;
  duration: string | null;
  measure: number;
  voice: number;
}

export interface EditorState {
  sessionId: string | null;
  session: SessionDetail | null;
  imageUrl: string | null;
  events: Record<string, EventInfo>;
  selected: Anchor | null;
  author: string;
  history: EditEvent[];
  cursor: number;
  startedAt: number | null;
  firstEditAt: number | null;
  interventions: Record<number, number>;

  loadSession: (session: SessionDetail, imageUrl: string) => void;
  setAuthor: (author: string) => void;
  selectAnchor: (anchor: Anchor) => void;
  recordEdit: (edit: EditEvent) => void;
  undo: () => void;
  redo: () => void;
  reset: () => void;
}

const INITIAL = {
  sessionId: null,
  session: null,
  imageUrl: null,
  events: {},
  selected: null,
  author: "transcriptor",
  history: [],
  cursor: 0,
  startedAt: null,
  firstEditAt: null,
  interventions: {},
} satisfies Partial<EditorState>;

/** Clave estable de un ancla (misma ruta lógica que el dominio). */
export function anchorKey(anchor: Anchor): string {
  return [
    anchor.part,
    anchor.staff,
    anchor.measure,
    anchor.voice,
    anchor.event_index,
    anchor.staff_id,
  ].join(":");
}

/** Indexa los eventos del `ScoreIR` por ancla, replicando `build_anchor_index`. */
export function collectEvents(document: ScoreDocument): Record<string, EventInfo> {
  const events: Record<string, EventInfo> = {};
  document.score.parts.forEach((part, partIndex) => {
    part.staves.forEach((staff, staffIndex) => {
      staff.measures.forEach((measure) => {
        const counters: Record<number, number> = {};
        measure.events.forEach((event) => {
          const index = counters[event.voice] ?? 0;
          counters[event.voice] = index + 1;
          const anchor: Anchor = {
            part: partIndex,
            staff: staffIndex,
            measure: measure.number,
            voice: event.voice,
            event_index: index,
            staff_id: staff.id,
            bbox: event.bbox,
            confidence: event.confidence,
          };
          events[anchorKey(anchor)] = {
            kind: event.kind,
            pitch: event.pitch,
            duration: event.duration_beats,
            measure: measure.number,
            voice: event.voice,
          };
        });
      });
    });
  });
  return events;
}

/** Altura vigente de un evento aplicando el log de ediciones hasta `cursor`. */
export function resolvePitch(
  events: Record<string, EventInfo>,
  history: EditEvent[],
  cursor: number,
  anchor: Anchor,
): string | null {
  const key = anchorKey(anchor);
  let pitch = events[key]?.pitch ?? null;
  for (const edit of history.slice(0, cursor)) {
    if (anchorKey(edit.anchor) !== key || edit.op !== "SetPitch") {
      continue;
    }
    const value = edit.after?.pitch;
    if (typeof value === "string") {
      pitch = value;
    }
  }
  return pitch;
}

function interventionsFrom(edits: EditEvent[]): Record<number, number> {
  return edits.reduce<Record<number, number>>((acc, edit) => {
    acc[edit.anchor.measure] = (acc[edit.anchor.measure] ?? 0) + 1;
    return acc;
  }, {});
}

export const useEditorStore = create<EditorState>((set) => ({
  ...INITIAL,

  loadSession: (session, imageUrl) =>
    set({
      sessionId: session.session_id,
      session,
      imageUrl,
      events: collectEvents(session.document),
      selected: null,
      history: session.edits,
      cursor: session.edits.length,
      startedAt: Date.now(),
      firstEditAt: session.edits.length > 0 ? Date.now() : null,
      interventions: interventionsFrom(session.edits),
    }),

  setAuthor: (author) => set({ author }),

  selectAnchor: (anchor) => set({ selected: anchor }),

  recordEdit: (edit) =>
    set((state) => {
      const history = [...state.history.slice(0, state.cursor), edit];
      return {
        history,
        cursor: history.length,
        firstEditAt: state.firstEditAt ?? Date.now(),
        interventions: {
          ...state.interventions,
          [edit.anchor.measure]: (state.interventions[edit.anchor.measure] ?? 0) + 1,
        },
      };
    }),

  undo: () => set((state) => ({ cursor: Math.max(0, state.cursor - 1) })),

  redo: () =>
    set((state) => ({ cursor: Math.min(state.history.length, state.cursor + 1) })),

  reset: () => set({ ...INITIAL }),
}));
