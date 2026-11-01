import { describe, expect, it } from "vitest";
import {
  appendScoreData,
  draftFromMetadata,
  emptyDraft,
  instrumentsSummary,
  INSTRUMENT_OPTIONS,
  metadataUpdate,
  sessionName,
  withInstrument,
} from "./scoreData";

describe("nombre de una sesión (#240)", () => {
  it("es el título; sin él, el archivo subido; sin ninguno, «Sesión» y el comienzo del id", () => {
    const id = "3e951fef-0000-4000-8000-000000000000";
    expect(sessionName({ session_id: id, title: "Mondnacht", source_filename: "p1.png" })).toBe(
      "Mondnacht",
    );
    expect(sessionName({ session_id: id, title: null, source_filename: "p1.png" })).toBe("p1.png");
    expect(sessionName({ session_id: id, title: "  ", source_filename: "" })).toBe(
      "Sesión 3e951fef",
    );
    expect(sessionName({ session_id: id })).toBe("Sesión 3e951fef");
  });
});

describe("instrumentos", () => {
  it("ofrece la lista cerrada de #235 con «Sin indicar» primero y «Otro» al final", () => {
    expect(INSTRUMENT_OPTIONS.map((option) => option.value)).toEqual([
      "",
      "voice",
      "piano",
      "violin",
      "cello",
      "flute",
      "clarinet",
      "guitar",
      "other",
    ]);
    expect(INSTRUMENT_OPTIONS.map((option) => option.label)).toEqual([
      "Sin indicar",
      "Voz",
      "Piano",
      "Violín",
      "Violonchelo",
      "Flauta",
      "Clarinete",
      "Guitarra",
      "Otro",
    ]);
  });

  it("resume los de cada parte, con el nombre dado si lo hay y sin las partes vacías del final", () => {
    expect(instrumentsSummary([])).toBeNull();
    expect(instrumentsSummary(undefined)).toBeNull();
    expect(
      instrumentsSummary([
        { instrument: "voice", name: null },
        { instrument: "piano", name: null },
      ]),
    ).toBe("Voz · Piano");
    expect(
      instrumentsSummary([
        { instrument: null, name: null },
        { instrument: "other", name: "Arpa" },
        { instrument: null, name: null },
      ]),
    ).toBe("Sin indicar · Arpa");
    expect(instrumentsSummary([{ instrument: "other", name: null }])).toBe("Otro");
    expect(instrumentsSummary([{ instrument: null, name: null }])).toBeNull();
  });

  it("al cambiar de instrumento se olvida el nombre del anterior", () => {
    const part = { instrument: "other" as const, name: "Arpa" };
    expect(withInstrument(part, "piano")).toEqual({ instrument: "piano", name: "" });
    expect(withInstrument(part, "other")).toEqual(part);
  });
});

describe("datos al transcribir", () => {
  const sent = (form: FormData) =>
    [...form.entries()].map(([key, value]) => [key, typeof value === "string" ? value : "file"]);

  it("sin datos no envía ningún campo: lo exportado es lo de siempre", () => {
    const form = new FormData();
    appendScoreData(form, emptyDraft(2));
    expect(sent(form)).toEqual([]);
  });

  it("recorta los textos y alinea instrumentos y nombres hasta la última parte con datos", () => {
    const form = new FormData();
    appendScoreData(form, {
      title: "  Mondnacht  ",
      composer: " Schumann ",
      parts: [
        { instrument: "", name: "" },
        { instrument: "other", name: "  Arpa " },
        { instrument: "", name: "" },
      ],
    });
    expect(sent(form)).toEqual([
      ["title", "Mondnacht"],
      ["composer", "Schumann"],
      ["instruments", ""],
      ["part_names", ""],
      ["instruments", "other"],
      ["part_names", "Arpa"],
    ]);
  });
});

describe("datos al cambiarlos (PATCH)", () => {
  it("parte de lo guardado, con una entrada por parte de la partitura", () => {
    expect(
      draftFromMetadata(
        { title: "Mondnacht", composer: null, instruments: [{ instrument: "voice", name: null }] },
        2,
      ),
    ).toEqual({
      title: "Mondnacht",
      composer: "",
      parts: [
        { instrument: "voice", name: "" },
        { instrument: "", name: "" },
      ],
    });
  });

  it("envía todo, con null para lo vacío y sin instrumentos si no hay ninguno", () => {
    expect(metadataUpdate({ title: " ", composer: " Clara ", parts: emptyDraft(2).parts })).toEqual(
      { title: null, composer: "Clara", instruments: [] },
    );
    expect(
      metadataUpdate({
        title: "Lied",
        composer: "",
        parts: [
          { instrument: "", name: "" },
          { instrument: "other", name: " Arpa " },
        ],
      }),
    ).toEqual({
      title: "Lied",
      composer: null,
      instruments: [
        { instrument: null, name: null },
        { instrument: "other", name: "Arpa" },
      ],
    });
  });

  it("sin partes que mostrar no toca los instrumentos guardados", () => {
    expect(metadataUpdate({ title: "Lied", composer: "", parts: [] })).toEqual({
      title: "Lied",
      composer: null,
    });
  });

  it("conserva el nombre guardado de una parte cuyo instrumento no cambia", () => {
    const draft = draftFromMetadata(
      { title: null, composer: null, instruments: [{ instrument: "voice", name: "Soprano" }] },
      1,
    );
    expect(metadataUpdate(draft).instruments).toEqual([{ instrument: "voice", name: "Soprano" }]);
  });
});
