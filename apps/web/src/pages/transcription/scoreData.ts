import type { Instrument, PartInstrumentRead, SessionMetadataUpdate } from "../../types";

/**
 * Los datos de una partitura que indica la persona (#240, ADR-0041, ADR-0045): su nombre, su
 * compositor y el instrumento de cada parte. Son datos de la sesión, no del `ScoreIR` ni del log.
 */

/** Límites del contrato, contados sobre el texto enviado (ya recortado). */
export const TITLE_MAX_LENGTH = 200;
export const COMPOSER_MAX_LENGTH = 200;
export const PART_NAME_MAX_LENGTH = 100;

/** Una parte en el formulario: `""` es «Sin indicar». */
export interface PartDraft {
  instrument: Instrument | "";
  /**
   * Nombre de la parte. El formulario solo lo pide con «Otro» (el nombre del instrumento); el que
   * ya tenga guardado otra parte se conserva mientras no se cambie su instrumento.
   */
  name: string;
}

/** Lo que se escribe en el formulario, tal cual: se recorta al enviar. */
export interface ScoreDataDraft {
  title: string;
  composer: string;
  parts: PartDraft[];
}

/** La lista cerrada de #235, en el orden del desplegable. «Otro» suena como el piano. */
export const INSTRUMENT_OPTIONS: readonly { value: Instrument | ""; label: string }[] = [
  { value: "", label: "Sin indicar" },
  { value: "voice", label: "Voz" },
  { value: "piano", label: "Piano" },
  { value: "violin", label: "Violín" },
  { value: "cello", label: "Violonchelo" },
  { value: "flute", label: "Flauta" },
  { value: "clarinet", label: "Clarinete" },
  { value: "guitar", label: "Guitarra" },
  { value: "other", label: "Otro" },
];

const INSTRUMENT_LABELS = new Map<string, string>(
  INSTRUMENT_OPTIONS.map((option) => [option.value, option.label]),
);

/** Nombre en español de un instrumento; uno que la web no conoce, por su identificador. */
export function instrumentLabel(instrument: string | null | undefined): string {
  return INSTRUMENT_LABELS.get(instrument ?? "") ?? instrument ?? "Sin indicar";
}

const emptyPart = (): PartDraft => ({ instrument: "", name: "" });

/** Sin nada indicado: no se envía ningún dato y la sesión se llama como el archivo. */
export function emptyDraft(parts: number): ScoreDataDraft {
  return { title: "", composer: "", parts: Array.from({ length: parts }, emptyPart) };
}

/** Cambia el instrumento de una parte: el nombre era el del anterior y se olvida. */
export function withInstrument(part: PartDraft, instrument: Instrument | ""): PartDraft {
  return instrument === part.instrument ? part : { instrument, name: "" };
}

/** Lo que se envía de una parte: su nombre solo si queda algo tras recortarlo. */
const partName = (part: PartDraft) => part.name.trim();
const hasData = (part: PartDraft) => part.instrument !== "" || partName(part) !== "";

/**
 * Añade los datos al formulario de `POST /transcribe`. Solo lo indicado: sin datos, la petición
 * es la de siempre. Instrumentos y nombres van alineados, uno por parte en el orden de la
 * partitura (de arriba abajo), hasta la última parte con datos; `''` es «sin indicar».
 */
export function appendScoreData(body: FormData, draft: ScoreDataDraft) {
  const title = draft.title.trim();
  const composer = draft.composer.trim();
  if (title) body.append("title", title);
  if (composer) body.append("composer", composer);
  let last = -1;
  draft.parts.forEach((part, index) => {
    if (hasData(part)) last = index;
  });
  for (const part of draft.parts.slice(0, last + 1)) {
    body.append("instruments", part.instrument);
    body.append("part_names", partName(part));
  }
}

/** Los datos guardados de una sesión, con una parte por cada una de su partitura. */
export function draftFromMetadata(
  metadata: {
    title?: string | null;
    composer?: string | null;
    instruments?: PartInstrumentRead[];
  },
  partCount: number,
): ScoreDataDraft {
  const saved = metadata.instruments ?? [];
  return {
    title: metadata.title ?? "",
    composer: metadata.composer ?? "",
    parts: Array.from({ length: partCount }, (_unused, index) => ({
      instrument: saved[index]?.instrument ?? "",
      name: saved[index]?.name ?? "",
    })),
  };
}

/**
 * El cuerpo de `PATCH /sessions/{id}`: todos los campos, con `null` para lo vacío. `instruments`
 * sustituye la lista entera; sin ninguno indicado, se quitan. Sin partes en el formulario (no se
 * sabe cuáles tiene la partitura) no se envía: lo que no se envía no cambia.
 */
export function metadataUpdate(draft: ScoreDataDraft): SessionMetadataUpdate {
  const texts = {
    title: draft.title.trim() || null,
    composer: draft.composer.trim() || null,
  };
  if (draft.parts.length === 0) return texts;
  return {
    ...texts,
    instruments: draft.parts.some(hasData)
      ? draft.parts.map((part) => ({
          instrument: part.instrument || null,
          name: partName(part) || null,
        }))
      : [],
  };
}

/** El texto recortado, o null si no queda nada. */
export function nonBlank(text: string | null | undefined): string | null {
  const trimmed = text?.trim();
  return trimmed === undefined || trimmed === "" ? null : trimmed;
}

/**
 * El nombre de una sesión en toda la web: su título; sin él, el nombre del archivo subido; sin
 * ninguno de los dos, «Sesión» y el comienzo de su identificador.
 */
export function sessionName(session: {
  session_id: string;
  title?: string | null;
  source_filename?: string | null;
}): string {
  return (
    nonBlank(session.title) ??
    nonBlank(session.source_filename) ??
    `Sesión ${session.session_id.slice(0, 8)}`
  );
}

/**
 * Los instrumentos de las partes, en su orden: el nombre dado o el del instrumento, «Sin indicar»
 * en una parte sin datos antes de otra que sí los tiene. Null si no hay ninguno.
 */
export function instrumentsSummary(instruments: PartInstrumentRead[] | undefined): string | null {
  const labels = (instruments ?? []).map((part) =>
    part.name?.trim() ? part.name.trim() : part.instrument ? instrumentLabel(part.instrument) : "",
  );
  while (labels.length > 0 && labels[labels.length - 1] === "") labels.pop();
  if (labels.length === 0) return null;
  return labels.map((label) => label || "Sin indicar").join(" · ");
}
