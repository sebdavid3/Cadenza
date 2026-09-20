import { afterEach, describe, expect, it, vi } from "vitest";

import type { Anchor } from "../types";
import { appendEdit, fetchSession } from "./client";

const ANCHOR: Anchor = {
  part: 0,
  staff: 0,
  measure: 1,
  voice: 0,
  event_index: 0,
  staff_id: "part-0-staff-0",
  bbox: null,
  confidence: null,
};

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchSession consulta /sessions/{id}", async () => {
    const payload = { session_id: "s1" };
    const mock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal("fetch", mock);

    const result = await fetchSession("s1");

    expect(mock).toHaveBeenCalledWith("/sessions/s1", undefined);
    expect(result).toEqual(payload);
  });

  it("lanza un error legible ante una respuesta no OK", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, text: async () => "nope" }),
    );

    await expect(fetchSession("x")).rejects.toThrow("API 404: nope");
  });

  it("appendEdit hace POST con JSON", async () => {
    const mock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "e1" }) });
    vi.stubGlobal("fetch", mock);

    await appendEdit("s1", { op: "SetPitch", anchor: ANCHOR, author: "tester" });

    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/sessions/s1/edits");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });
});
