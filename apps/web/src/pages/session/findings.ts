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

/** Agrupa los hallazgos activos por compás, en el orden de la partitura. */
export function measureMarks(score: ScoreIRPayload, active: readonly FindingRead[]): MeasureMark[] {
  const marks = new Map<string, MeasureMark>();
  for (const finding of active) {
    const slot = measureSlot(score, finding.anchor);
    if (!slot) continue;
    const key = slotKey(slot);
    const mark = marks.get(key);
    if (mark) mark.findings.push(finding);
    else marks.set(key, { key, slot, measureNumber: finding.anchor.measure, findings: [finding] });
  }
  return [...marks.values()].sort(
    (a, b) => a.slot.staff - b.slot.staff || a.slot.measure - b.slot.measure,
  );
}

/**
 * Los hallazgos de `latest_only` son de la última validación. Si se editó después, describen un
 * estado anterior: se devuelve ese estado para avisarlo.
 */
export function staleValidationSeq(
  findings: readonly FindingRead[],
  currentSeq: number,
): number | null {
  const seqs = findings.map((finding) => finding.at_seq ?? 0);
  if (seqs.length === 0) return null;
  const validated = Math.max(...seqs);
  return validated < currentSeq ? validated : null;
}
