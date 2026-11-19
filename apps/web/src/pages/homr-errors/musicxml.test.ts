import { describe, expect, it } from "vitest";
import type { DrawnEventRead, FigureRead } from "../../types";
import { barMusicXml } from "./musicxml";

const figure = (...parts: [string, number, number, boolean?][]): FigureRead => ({
  name: parts.map(([name]) => name).join(" + "),
  symbol: parts.map(([name, dots, tuplet, grace = false]) => ({
    figure: name,
    dots,
    tuplet,
    grace,
  })),
});

const FIGURES: Record<string, FigureRead> = {
  "1": figure(["negra", 0, 0]),
  "1/2": figure(["corchea", 0, 0]),
  "3/2": figure(["negra", 1, 0]),
  "1/3": figure(["corchea", 0, 3]),
  "5/4": figure(["negra", 0, 0], ["semicorchea", 0, 0]),
  "0": figure(["corchea", 0, 0, true]),
};

const note = (pitch: string, beats: string, chord = false): DrawnEventRead => ({
  kind: "note",
  pitch,
  beats,
  chord,
});
const rest = (beats: string): DrawnEventRead => ({ kind: "rest", pitch: "", beats, chord: false });

function parse(xml: string | null): Document {
  expect(xml).not.toBeNull();
  const document = new DOMParser().parseFromString(xml ?? "", "application/xml");
  expect(document.getElementsByTagName("parsererror")).toHaveLength(0);
  return document;
}

const text = (document: Document, selector: string) =>
  [...document.querySelectorAll(selector)].map((element) => element.textContent);

describe("el compás de un ejemplo en MusicXML, para grabarlo con OSMD", () => {
  it("lleva su clave, su armadura y una métrica oculta que suma lo que dura", () => {
    const document = parse(
      barMusicXml(
        "F4",
        -2,
        [note("Bb2", "3/2"), note("C3", "1/2"), rest("1")],
        1,
        FIGURES,
        "#7a2cf0",
      ),
    );

    expect(text(document, "clef sign")).toEqual(["F"]);
    expect(text(document, "clef line")).toEqual(["4"]);
    expect(text(document, "key fifths")).toEqual(["-2"]);
    // 3/2 + 1/2 + 1 = 3 negras: 3/4, sin dibujar.
    expect(document.querySelector("time")?.getAttribute("print-object")).toBe("no");
    expect(text(document, "time beats")).toEqual(["3"]);
    expect(text(document, "time beat-type")).toEqual(["4"]);
    expect(text(document, "divisions")).toEqual(["2"]);
    expect(text(document, "note duration")).toEqual(["3", "1", "2"]);
    expect(text(document, "note type")).toEqual(["quarter", "eighth", "quarter"]);
    expect(document.querySelectorAll("note")[0]?.querySelectorAll("dot")).toHaveLength(1);
    expect(text(document, "pitch step")).toEqual(["B", "C"]);
    expect(text(document, "pitch alter")).toEqual(["-1"]);
    expect(text(document, "pitch octave")).toEqual(["2", "3"]);
    expect(document.querySelectorAll("rest")).toHaveLength(1);
  });

  it("pinta en violeta solo la nota del ejemplo", () => {
    const document = parse(
      barMusicXml("G2", 0, [note("C5", "1"), note("D5", "1")], 1, FIGURES, "#7a2cf0"),
    );
    const notes = document.querySelectorAll("note");

    expect(notes[0]?.getAttribute("color")).toBeNull();
    expect(notes[1]?.getAttribute("color")).toBe("#7a2cf0");
    expect(notes[1]?.querySelector("notehead")?.getAttribute("color")).toBe("#7a2cf0");
  });

  it("escribe tresillos, acordes, notas de adorno y figuras ligadas", () => {
    const document = parse(
      barMusicXml(
        "G2-1",
        3,
        [
          note("E4", "0"),
          note("C4", "1/3"),
          note("E4", "1/3", true),
          note("D4", "1/3"),
          note("E4", "1/3"),
          note("G4", "5/4"),
        ],
        null,
        FIGURES,
        "#7a2cf0",
      ),
    );
    const notes = [...document.querySelectorAll("note")];

    expect(text(document, "clef-octave-change")).toEqual(["-1"]);
    // De adorno, sin duración.
    expect(notes[0]?.querySelector("grace")).not.toBeNull();
    expect(notes[0]?.querySelector("duration")).toBeNull();
    // El acorde: la segunda nota lleva <chord/>; el tresillo, su time-modification.
    expect(notes[2]?.querySelector("chord")).not.toBeNull();
    expect(text(document, "time-modification actual-notes")).toEqual(["3", "3", "3", "3"]);
    expect(text(document, "time-modification normal-notes")).toEqual(["2", "2", "2", "2"]);
    // Negra + semicorchea, ligadas.
    expect(notes[5]?.querySelector('tie[type="start"]')).not.toBeNull();
    expect(notes[6]?.querySelector('tie[type="stop"]')).not.toBeNull();
    expect(notes[6]?.querySelector("type")?.textContent).toBe("16th");
    // 1 + 5/4 = 9/4 negras: divisiones de 12 (tercios y cuartos de negra) y métrica de 9/16.
    expect(text(document, "divisions")).toEqual(["12"]);
    expect(text(document, "time beats")).toEqual(["9"]);
    expect(text(document, "time beat-type")).toEqual(["16"]);
  });

  it("sin nada leído, un silencio de compás que no se ve", () => {
    const document = parse(barMusicXml("G2", 0, [], null, FIGURES, "#7a2cf0"));

    expect(document.querySelector("note")?.getAttribute("print-object")).toBe("no");
    expect(document.querySelector("rest")?.getAttribute("measure")).toBe("yes");
  });

  it("no escribe lo que no tiene figura ni una altura que no se entiende", () => {
    expect(barMusicXml("G2", 0, [note("C5", "7/5")], null, FIGURES, "#7a2cf0")).toBeNull();
    expect(barMusicXml("G2", 0, [note("H9", "1")], null, FIGURES, "#7a2cf0")).toBeNull();
  });
});
