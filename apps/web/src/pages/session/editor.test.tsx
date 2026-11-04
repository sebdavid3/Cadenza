import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { createApiClient } from "../../api/client";
import { deferred, jsonResponse, mockApi } from "../../test/auth-helpers";
import type { AnchorPayload, ScoreEventPayload, SessionDetailRead } from "../../types";
import { useEditor } from "./editor";

const ID = "sesion";
const ANCHOR: AnchorPayload = {
  part: 0,
  staff: 0,
  measure: 1,
  voice: 0,
  event_index: 0,
  staff_id: "part-0-staff-0",
  bbox: null,
  confidence: null,
};
const EVENT: ScoreEventPayload = {
  kind: "note",
  voice: 0,
  pitch: "C4",
  duration_beats: "1",
  tie: null,
  is_chord: false,
  bbox: null,
  confidence: null,
  ir_handle: null,
};
const DETAIL = {
  session_id: ID,
  current_seq: 0,
  status: "transcribed",
  edits: [],
  current_score: {
    parts: [
      {
        id: "part-0",
        staves: [{ id: "part-0-staff-0", measures: [{ number: 1, events: [EVENT] }] }],
      },
    ],
  },
} as unknown as SessionDetailRead;

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const api = createApiClient({ baseUrl: "/api" });
  return renderHook(() => useEditor(api, ID, DETAIL), { wrapper });
}

describe("useEditor", () => {
  it("envía una sola edición aunque lleguen dos órdenes antes de volver a pintar", async () => {
    const pending = deferred<Response>();
    const { calls } = mockApi({
      [`POST /sessions/${ID}/edits`]: () => pending.promise,
      [`GET /sessions/${ID}`]: () => jsonResponse(DETAIL),
    });
    const { result } = setup();
    const target = { anchor: ANCHOR, event: EVENT, chord: false };

    // Las dos con el mismo render: la guarda de la petición en curso es lo único que las separa.
    act(() => {
      result.current.run({ kind: "step", direction: 1 }, target);
      result.current.run({ kind: "step", direction: -1 }, target);
    });

    expect(calls.filter((call) => call.key === `POST /sessions/${ID}/edits`)).toHaveLength(1);
    pending.resolve(jsonResponse({ seq: 1 }, 201));
    await waitFor(() => {
      expect(result.current.status.kind).not.toBe("saving");
    });
  });
});
