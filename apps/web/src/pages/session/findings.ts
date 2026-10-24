import type { AnchorPayload, FindingRead, ScoreIRPayload } from "../../types";

/**
 * Familias de reglas del validador (`packages/validation`) con un nombre que se entienda. Una
 * regla nueva sin nombre aquí se muestra con su identificador.
 */
const RULE_LABELS: Record<string, string> = {
  "measure.balance": "Duración del compás",
  "key.consistency": "Armadura y alteraciones",
  "pitch.range": "Altura fuera de registro",
  "tie.resolution": "Ligadura sin cerrar",
  "voice.collision": "Voces que se pisan",
};

export function ruleLabel(ruleId: string): string {
  return RULE_LABELS[ruleId] ?? ruleId;
}

/** Hallazgos activos (los que se marcan) y descartados como falso positivo. */
export function splitFindings(findings: readonly FindingRead[]) {
  const active: FindingRead[] = [];
  const dismissed: FindingRead[] = [];
  for (const finding of findings) {
    if (finding.status === "dismissed") dismissed.push(finding);
    else active.push(finding);
  }
  return { active, dismissed };
}

/** Posición de un compás en la partitura dibujada: pentagrama global y compás desde 0. */
export interface MeasureSlot {
  staff: number;
  measure: number;
}

/**
 * Dónde cae el compás de un ancla. OSMD numera los pentagramas de todas las partes seguidos y
 * los compases por posición, así que se cuenta por posición en el `ScoreIR` (ADR-0021).
 */
export function measureSlot(score: ScoreIRPayload, anchor: AnchorPayload): MeasureSlot | null {
  const part = score.parts[anchor.part];
  const staff = part?.staves[anchor.staff];
  if (!part || !staff) return null;
  const measure = staff.measures.findIndex((candidate) => candidate.number === anchor.measure);
  if (measure < 0) return null;
  const previousStaves = score.parts
    .slice(0, anchor.part)
    .reduce((total, previous) => total + previous.staves.length, 0);
  return { staff: previousStaves + anchor.staff, measure };
}

/** Número de compases de cada pentagrama, en el orden global de OSMD. */
export function measuresPerStaff(score: ScoreIRPayload): number[] {
  return score.parts.flatMap((part) => part.staves.map((staff) => staff.measures.length));
}

/** Compás marcado en la partitura y los hallazgos que lo señalan. */
export interface MeasureMark {
  key: string;
  slot: MeasureSlot;
  measureNumber: number;
  findings: FindingRead[];
}

export function slotKey(slot: MeasureSlot): string {
  return `${String(slot.staff)}:${String(slot.measure)}`;
}

/**
 * Agrupa los hallazgos activos por compás, en el orden de la partitura. Los que no caen en
 * ningún compás de la partitura no se marcan, pero se devuelven aparte para listarlos igual.
 */
export function measureMarks(
  score: ScoreIRPayload,
  active: readonly FindingRead[],
): { marks: MeasureMark[]; unplaced: FindingRead[] } {
  const marks = new Map<string, MeasureMark>();
  const unplaced: FindingRead[] = [];
  for (const finding of active) {
    const slot = measureSlot(score, finding.anchor);
    if (!slot) {
      unplaced.push(finding);
      continue;
    }
    const key = slotKey(slot);
    const mark = marks.get(key);
    if (mark) mark.findings.push(finding);
    else marks.set(key, { key, slot, measureNumber: finding.anchor.measure, findings: [finding] });
  }
  const sorted = [...marks.values()].sort(
    (a, b) => a.slot.staff - b.slot.staff || a.slot.measure - b.slot.measure,
  );
  return { marks: sorted, unplaced };
}

/**
 * De qué estado es la última validación respecto al que se ve (ADR-0013, ADR-0035):
 * - `current`: del estado actual;
 * - `stale`: de un estado anterior (`seq`), porque se editó después;
 * - `ahead`: de un estado posterior al que se ve, porque se editó y se revalidó en otra pestaña
 *   o dispositivo y la vista todavía no lo ha cargado;
 * - `unknown`: sin hallazgos no hay `at_seq` que comparar (`SessionDetailRead` no expone
 *   `validated_at_seq`) y la partitura tiene ediciones (ADR-0021 §3).
 */
export type ValidationState =
  { kind: "current" } | { kind: "stale"; seq: number } | { kind: "ahead" } | { kind: "unknown" };

/**
 * Los hallazgos de `latest_only` son de la última validación, también los descartados. `knownSeq`
 * es el estado de una validación que se sabe hecha (la que devolvió `POST /validate`): sin
 * hallazgos, es lo único que dice de cuándo es. Vale la más reciente de las dos.
 */
export function validationState(
  findings: readonly FindingRead[],
  currentSeq: number,
  knownSeq: number | null = null,
): ValidationState {
  const seqs = findings.map((finding) => finding.at_seq ?? 0);
  if (knownSeq !== null) seqs.push(knownSeq);
  // Sin ediciones, la única validación es la de la transcripción, sobre el estado 0.
  if (seqs.length === 0) return currentSeq === 0 ? { kind: "current" } : { kind: "unknown" };
  const validated = Math.max(...seqs);
  if (validated > currentSeq) return { kind: "ahead" };
  return validated < currentSeq ? { kind: "stale", seq: validated } : { kind: "current" };
}

/** La lista con `updated` en lugar del hallazgo con su mismo id (tras descartarlo o restaurarlo). */
export function withFinding(findings: readonly FindingRead[], updated: FindingRead): FindingRead[] {
  return findings.map((finding) => (finding.id === updated.id ? updated : finding));
}

/**
 * Dónde está un posible error, para nombrar sus acciones y decir qué se hizo con él: «compás 3».
 * Con varios pentagramas, también en cuál (en el orden global de OSMD, como las marcas).
 */
export function findingPlace(
  score: ScoreIRPayload | null,
  finding: FindingRead,
  multiStaff: boolean,
): string {
  const { anchor } = finding;
  const place = `compás ${String(anchor.measure)}`;
  if (!multiStaff || !score) return place;
  const previousStaves = score.parts
    .slice(0, anchor.part)
    .reduce((total, previous) => total + previous.staves.length, 0);
  return `${place} del pentagrama ${String(previousStaves + anchor.staff + 1)}`;
}

/** Qué posible error es y dónde: «Duración del compás, compás 3». */
export function findingLabel(
  score: ScoreIRPayload | null,
  finding: FindingRead,
  multiStaff: boolean,
): string {
  return `${ruleLabel(finding.rule_id)}, ${findingPlace(score, finding, multiStaff)}`;
}
