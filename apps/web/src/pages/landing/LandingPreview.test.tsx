import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../router";
import { ANA, fakeJwt, jsonResponse, resetAuth, signInAs } from "../../test/auth-helpers";
import { mockApiWithInstantJobs } from "../../test/jobs";
import type { PreviewResponse } from "../../types";
import { PENDING_CLAIM_KEY, useLandingUpload } from "./uploadStore";

// OSMD no dibuja en jsdom: la partitura es un doble que dice qué recibe.
vi.mock("../session/ScoreView", () => ({
  ScoreView: (props: { snapshot: { xml: string }; notesSelectable?: boolean }) => (
    <div
      data-testid="partitura"
      data-xml={props.snapshot.xml}
      data-selectable={String(props.notesSelectable ?? true)}
    />
  ),
}));
vi.mock("../session/toneEngine", () => ({
  createToneEngine: () => ({
    play: () => Promise.resolve(),
    pause: () => undefined,
    stop: () => undefined,
    setTempo: () => undefined,
    update: () => undefined,
    dispose: () => undefined,
  }),
}));

const PREVIEW_ID = "8d0e1c2b-0000-4a52-9e0c-3f4a5b6c7d8e";
const SESSION_ID = "5c1f0e8e-2b7d-4a52-9e0c-3f4a5b6c7d8e";
const XML = "<score-partwise>sin cuenta</score-partwise>";
/** Token de prueba generado en cada ejecución. */
const CLAIM_TOKEN = `t-${crypto.randomUUID()}`;
const secret = () => `p-${crypto.randomUUID()}`;

function previewResponse(changes: Partial<PreviewResponse> = {}): PreviewResponse {
  const anchor = {
    part: 0,
    staff: 0,
    measure: 1,
    voice: 0,
    event_index: 0,
    staff_id: "part-0-staff-0",
    bbox: null,
    confidence: null,
  };
  return {
    preview_id: PREVIEW_ID,
    claim_token: CLAIM_TOKEN,
    expires_at: new Date(Date.now() + 3_600_000).toISOString(),
    findings_count: 3,
    musicxml: XML,
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
                  events: [
                    {
                      kind: "note",
                      voice: 0,
                      pitch: "C4",
                      duration_beats: "3",
                      tie: null,
                      is_chord: false,
                      bbox: null,
                      confidence: null,
                      ir_handle: null,
                    },
                  ],
                  time_signature: { beats: 3, beat_type: 4 },
                },
              ],
            },
          ],
        },
      ],
    },
    timing: {
      session_id: PREVIEW_ID,
      total_beats: "3",
      measure_offsets: { "1": "0" },
      events: [
        {
          anchor,
          kind: "note",
          measure_number: 1,
          voice: 0,
          offset_beats: "0",
          duration_beats: "3",
          measure_offset_beats: "0",
        },
      ],
    },
    title: "Minueto",
    composer: null,
    instruments: [],
    source_filename: "minueto.png",
    ...changes,
  };
}

const claimed = () =>
  jsonResponse(
    {
      session_id: SESSION_ID,
      document_id: "homr-1",
      omr_engine: "homr",
      findings_count: 3,
      condition: "assisted",
      test_score_id: null,
    },
    201,
  );

const loginRoutes = {
  "POST /auth/login": () => jsonResponse({ access_token: fakeJwt(1_800_000) }),
  "GET /auth/me": () => jsonResponse(ANA),
};

function png(name = "minueto.png") {
  return new File([new Uint8Array(8)], name, { type: "image/png" });
}

function renderAt(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

function box() {
  return screen.getByRole("region", { name: /transcribe una partitura/i });
}

function fileInput(): HTMLInputElement {
  const input = box().querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("falta el selector de archivos de la portada");
  return input;
}

async function logInThroughForm() {
  await userEvent.type(screen.getByLabelText("Usuario"), "ana");
  await userEvent.type(screen.getByLabelText("Contraseña"), secret());
  await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
}

const scrollIntoView = vi.fn();

beforeEach(() => {
  resetAuth();
  useLandingUpload.getState().reset();
  vi.stubEnv("VITE_ANONYMOUS_PREVIEW_ENABLED", "true");
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    value: scrollIntoView,
    configurable: true,
    writable: true,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  useLandingUpload.getState().reset();
});

describe("transcribir sin cuenta desde la portada (#278)", () => {
  it("sin sesión transcribe sin token y enseña el resultado en solo lectura, con «Entrar para editarla»", async () => {
    const { calls } = mockApiWithInstantJobs({
      "POST /previews": () => jsonResponse(previewResponse(), 201),
    });
    renderAt();

    await userEvent.upload(fileInput(), png());
    expect(within(box()).getByText(/se guarda una hora/i)).toBeVisible();
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    const result = await within(box()).findByRole("region", { name: "Minueto" });
    const call = calls.find((candidate) => candidate.key === "POST /previews");
    expect(new Headers(call?.init?.headers).get("Authorization")).toBeNull();
    expect(within(result).getByText("3 posibles errores")).toBeVisible();
    expect(within(result).getByTestId("partitura")).toHaveAttribute("data-xml", XML);
    expect(within(result).getByTestId("partitura")).toHaveAttribute("data-selectable", "false");
    expect(within(result).getByRole("button", { name: /reproducir/i })).toBeVisible();
    expect(within(result).getByRole("link", { name: "Entrar para editarla" })).toBeVisible();
    expect(within(result).getByText(/se guarda hasta las/i)).toBeVisible();
    // Se apunta cómo reclamarla, no la imagen.
    const stored = JSON.parse(sessionStorage.getItem(PENDING_CLAIM_KEY) ?? "null") as {
      id: string;
      token: string;
    } | null;
    expect(stored).toMatchObject({ id: PREVIEW_ID, token: CLAIM_TOKEN });
    expect(sessionStorage.getItem(PENDING_CLAIM_KEY)).not.toMatch(/data:|base64/);
    expect(calls.some((candidate) => candidate.key === "POST /transcription-jobs")).toBe(false);
  });

  it("«Entrar para editarla» lleva a entrar y, al volver, la reclama y abre su sesión", async () => {
    const { calls } = mockApiWithInstantJobs({
      "POST /previews": () => jsonResponse(previewResponse(), 201),
      [`POST /previews/${PREVIEW_ID}/claim`]: claimed,
      ...loginRoutes,
    });
    const router = renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));
    const result = await within(box()).findByRole("region", { name: "Minueto" });

    await userEvent.click(within(result).getByRole("link", { name: "Entrar para editarla" }));
    expect(router.state.location.pathname).toBe("/entrar");
    await logInThroughForm();

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/sesiones/${SESSION_ID}`);
    });
    const claim = calls.find((candidate) => candidate.key === `POST /previews/${PREVIEW_ID}/claim`);
    const body = claim?.init?.body;
    expect(typeof body === "string" ? (JSON.parse(body) as unknown) : null).toEqual({
      claim_token: CLAIM_TOKEN,
    });
    expect(new Headers(claim?.init?.headers).get("Authorization")).toMatch(/^Bearer /);
    expect(sessionStorage.getItem(PENDING_CLAIM_KEY)).toBeNull();
    expect(calls.filter((candidate) => candidate.key === "POST /previews")).toHaveLength(1);
  });

  it("tras una recarga, volver de entrar reclama la transcripción apuntada", async () => {
    sessionStorage.setItem(
      PENDING_CLAIM_KEY,
      JSON.stringify({
        id: PREVIEW_ID,
        token: CLAIM_TOKEN,
        expiresAt: Date.now() + 600_000,
        name: "Minueto",
      }),
    );
    mockApiWithInstantJobs({ [`POST /previews/${PREVIEW_ID}/claim`]: claimed });
    signInAs(ANA);

    const router = renderAt("/#transcribir");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/sesiones/${SESSION_ID}`);
    });
  });

  it("tras una recarga sin sesión, dice que hay una transcripción pendiente y pide entrar", () => {
    sessionStorage.setItem(
      PENDING_CLAIM_KEY,
      JSON.stringify({
        id: PREVIEW_ID,
        token: CLAIM_TOKEN,
        expiresAt: Date.now() + 600_000,
        name: "Minueto",
      }),
    );
    mockApiWithInstantJobs({});
    renderAt("/#transcribir");

    const pending = within(box()).getByRole("region", { name: /transcripción sin cuenta/i });
    expect(pending).toHaveTextContent("«Minueto» está transcrita sin cuenta");
    expect(within(pending).getByRole("link", { name: "Entrar para editarla" })).toBeVisible();
  });

  it("con el servidor sin transcripción sin cuenta (404), vuelve a pedir que se entre", async () => {
    const { calls } = mockApiWithInstantJobs({
      "POST /previews": () => jsonResponse({ detail: "Not Found" }, 404),
    });
    renderAt();
    await userEvent.upload(fileInput(), png());

    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    expect(
      await within(box()).findByText(/ahora no se puede transcribir sin cuenta/i),
    ).toBeVisible();
    expect(within(box()).getByRole("link", { name: "Entrar y transcribir" })).toBeVisible();
    expect(within(box()).queryByRole("button", { name: "Transcribir la imagen" })).toBeNull();
    expect(calls.filter((call) => call.key === "POST /previews")).toHaveLength(1);
  });

  it("si la transcripción sin cuenta caducó al reclamarla, ofrece transcribir la imagen con la cuenta", async () => {
    const { calls } = mockApiWithInstantJobs({
      "POST /previews": () => jsonResponse(previewResponse(), 201),
      [`POST /previews/${PREVIEW_ID}/claim`]: () => jsonResponse({ detail: "x" }, 404),
      "POST /transcribe": () =>
        jsonResponse(
          {
            session_id: SESSION_ID,
            document_id: "homr-1",
            omr_engine: "homr",
            findings_count: 0,
            condition: "assisted",
            test_score_id: null,
          },
          201,
        ),
      [`GET /sessions/${SESSION_ID}`]: () => jsonResponse({ detail: "x" }, 500),
    });
    renderAt();
    await userEvent.upload(fileInput(), png());
    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));
    const result = await within(box()).findByRole("region", { name: "Minueto" });
    signInAs(ANA);

    await userEvent.click(await within(result).findByRole("button", { name: "Editar" }));

    expect(await within(box()).findByText(/ya no está: caduca a la hora/i)).toBeVisible();
    await userEvent.click(within(box()).getByRole("button", { name: "Volver a intentarlo" }));
    await waitFor(() => {
      expect(calls.some((call) => call.key === "POST /transcription-jobs")).toBe(true);
    });
  });

  it("el límite por conexión dice cuándo volver a probar", async () => {
    mockApiWithInstantJobs({
      "POST /previews": () =>
        new Response(JSON.stringify({ detail: "x" }), {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "1800" },
        }),
    });
    renderAt();
    await userEvent.upload(fileInput(), png());

    await userEvent.click(within(box()).getByRole("button", { name: "Transcribir la imagen" }));

    expect(await within(box()).findByRole("alert")).toHaveTextContent(
      /vuelve a probar en 30 minutos o entra con tu cuenta/i,
    );
  });

  it("sin el build que lo abre, sin sesión se pide entrar como antes", async () => {
    vi.stubEnv("VITE_ANONYMOUS_PREVIEW_ENABLED", "");
    mockApiWithInstantJobs({});
    renderAt();

    await userEvent.upload(fileInput(), png());

    expect(within(box()).getByText(/para transcribir hace falta entrar/i)).toBeVisible();
    expect(within(box()).queryByRole("button", { name: "Transcribir la imagen" })).toBeNull();
  });
});
