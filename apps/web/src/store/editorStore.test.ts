import { beforeEach, describe, expect, it } from "vitest";

import type { Anchor, EditEvent, SessionDetail } from "../types";
import { anchorKey, collectEvents, resolvePitch, useEditorStore } from "./editorStore";

const ANCHOR: Anchor = {
  part: 0,
  staff: 0,
  measure: 1,
  voice: 0,
  event_index: 0,
  staff_id: "part-0-staff-0",
  bbox: [0, 0, 10, 10],
  confidence: null,
};

function session(): SessionDetail {
  return {
    session_id: "s1",
    document_id: "doc-1",
    omr_engine: "fake",
    document: {
      id: "doc-1",
      score: {
        parts: [
          {
            id: "part-0",
            staves: [
              {
                id: "part-0-staff-0",
                measures: [
                  {
                    number: 1,
                    time_signature: { beats: 4, beat_type: 4 },
                    events: [
                      {
                        kind: "note",
                        voice: 0,
                        pitch: "C4",
                        duration_beats: "1",
                        bbox: [0, 0, 10, 10],
                        confidence: null,
                        ir_handle: null,
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
      anchors: {
        entries: [
          {
            anchor: ANCHOR,
            event: { kind: "note", ir_handle: null, bbox: [0, 0, 10, 10], confidence: null },
          },
        ],
      },
      provenance: {
        omr_engine: "fake",
        model_version: null,
        rules_version: null,
        source_image_hash: null,
        created_at: null,
      },
    },
    findings: [],
    edits: [],
  };
}

function edit(seq: number, pitch: string): EditEvent {
  return {
    id: `e${seq}`,
    session_id: "s1",
    seq,
    op: "SetPitch",
    author: "tester",
    anchor: ANCHOR,
    before: null,
    after: { pitch },
    created_at: "2026-09-20T00:00:00Z",
  };
}

describe("editorStore", () => {
  beforeEach(() => {
    useEditorStore.getState().reset();
  });

  it("indexa los eventos del ScoreIR por ancla", () => {
    const events = collectEvents(session().document);
    expect(events[anchorKey(ANCHOR)]?.pitch).toBe("C4");
  });

  it("resuelve la altura aplicando el log hasta el cursor", () => {
    const events = collectEvents(session().document);
    const history = [edit(1, "D4"), edit(2, "E4")];
    expect(resolvePitch(events, history, 0, ANCHOR)).toBe("C4");
    expect(resolvePitch(events, history, 1, ANCHOR)).toBe("D4");
    expect(resolvePitch(events, history, 2, ANCHOR)).toBe("E4");
  });

  it("registra ediciones, métricas y undo/redo", () => {
    const store = useEditorStore.getState();
    store.loadSession(session(), "blob:image");
    store.recordEdit(edit(1, "D4"));
    store.recordEdit(edit(2, "E4"));

    const applied = useEditorStore.getState();
    expect(applied.cursor).toBe(2);
    expect(applied.interventions[1]).toBe(2);
    expect(applied.firstEditAt).not.toBeNull();

    applied.undo();
    expect(useEditorStore.getState().cursor).toBe(1);
    useEditorStore.getState().redo();
    expect(useEditorStore.getState().cursor).toBe(2);
  });

  it("trunca el futuro al registrar tras deshacer", () => {
    const store = useEditorStore.getState();
    store.loadSession(session(), "blob:image");
    store.recordEdit(edit(1, "D4"));
    store.recordEdit(edit(2, "E4"));
    store.undo();
    store.recordEdit(edit(3, "F4"));

    const state = useEditorStore.getState();
    expect(state.history.map((item) => item.seq)).toEqual([1, 3]);
    expect(state.cursor).toBe(2);
  });

  it("carga las ediciones persistidas de la sesión", () => {
    const withEdits = session();
    withEdits.edits = [edit(1, "D4")];
    useEditorStore.getState().loadSession(withEdits, "blob:image");

    const state = useEditorStore.getState();
    expect(state.cursor).toBe(1);
    expect(state.interventions[1]).toBe(1);
    expect(resolvePitch(state.events, state.history, state.cursor, ANCHOR)).toBe("D4");
  });
});
