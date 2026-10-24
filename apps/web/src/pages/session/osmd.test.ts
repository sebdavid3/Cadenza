import { describe, expect, it } from "vitest";
import { withInitialAttributes } from "./osmd";

/** MusicXML de una parte con los compases dados (el contenido de cada `<measure>`). */
function score(...measures: string[]): Document {
  const body = measures
    .map((content, index) => `<measure number="${String(index + 1)}">${content}</measure>`)
    .join("");
  return new DOMParser().parseFromString(
    `<score-partwise version="4.0"><part id="P1">${body}</part></score-partwise>`,
    "application/xml",
  );
}

const NOTE = "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>";

/** Los hijos de `<attributes>` de un compás, con la quinta o el signo y la línea. */
function attributesOf(document: Document, measure: number): string[] {
  const element = document.getElementsByTagName("measure")[measure - 1];
  const attributes = element?.getElementsByTagName("attributes")[0];
  return [...(attributes?.children ?? [])].map((child) => {
    const number = child.getAttribute("number");
    const text = [...child.children].map((part) => part.textContent).join("");
    return `${child.localName}${number ? `#${number}` : ""}${text ? `:${text}` : ""}`;
  });
}

describe("armadura y clave del primer compás para OSMD (ADR-0033)", () => {
  it("escribe «sin alteraciones» en el primer compás si la primera armadura es de otro", () => {
    const document = withInitialAttributes(
      score(
        `<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>${NOTE}`,
        `<attributes><key><fifths>2</fifths></key></attributes>${NOTE}`,
      ),
    );
    // En el orden de MusicXML: tras `divisions` y antes de `time`.
    expect(attributesOf(document, 1)).toEqual(["divisions", "key:0", "time:44", "clef:G2"]);
    expect(attributesOf(document, 2)).toEqual(["key:2"]);
  });

  it("no toca una partitura con armadura en el primer compás, ni una sin ninguna", () => {
    const withKey = score(
      `<attributes><divisions>1</divisions><key><fifths>-1</fifths></key><clef><sign>F</sign><line>4</line></clef></attributes>${NOTE}`,
      `<attributes><key><fifths>2</fifths></key></attributes>${NOTE}`,
    );
    expect(attributesOf(withInitialAttributes(withKey), 1)).toEqual([
      "divisions",
      "key:-1",
      "clef:F4",
    ]);
    const without = score(`<attributes><divisions>1</divisions></attributes>${NOTE}`, NOTE);
    expect(attributesOf(withInitialAttributes(without), 1)).toEqual(["divisions"]);
  });

  it("escribe la clave de sol en el primer compás si la primera clave es de otro", () => {
    const document = withInitialAttributes(
      score(
        `<print/><attributes><divisions>1</divisions><key><fifths>0</fifths></key></attributes>${NOTE}`,
        `<attributes><clef><sign>F</sign><line>4</line></clef></attributes>${NOTE}`,
      ),
    );
    expect(attributesOf(document, 1)).toEqual(["divisions", "key:0", "clef:G2"]);
  });

  it("crea `<attributes>` en el primer compás si no lo tiene, tras `<print>`", () => {
    const document = withInitialAttributes(
      score(`<print/>${NOTE}`, `<attributes><key><fifths>3</fifths></key></attributes>${NOTE}`),
    );
    const first = document.getElementsByTagName("measure")[0];
    expect([...(first?.children ?? [])].map((child) => child.localName)).toEqual([
      "print",
      "attributes",
      "note",
    ]);
    expect(attributesOf(document, 1)).toEqual(["key:0"]);
  });

  it("en un piano, solo la clave del pentagrama que no la tiene, con su número", () => {
    const document = withInitialAttributes(
      score(
        `<attributes><divisions>1</divisions><key><fifths>0</fifths></key><staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef></attributes>${NOTE}`,
        `<attributes><clef number="2"><sign>F</sign><line>4</line></clef></attributes>${NOTE}`,
      ),
    );
    expect(attributesOf(document, 1)).toEqual([
      "divisions",
      "key:0",
      "staves",
      "clef#1:G2",
      "clef#2:G2",
    ]);
  });
});
