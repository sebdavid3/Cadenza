/** Contratos del dominio expuestos por la API (primitivos de `ScoreDocument`). */

export type BBox = [number, number, number, number];

export type EventKind = "note" | "rest" | "clef" | "key" | "time";

export interface Anchor {
  part: number;
  staff: number;
  measure: number;
  voice: number;
  event_index: number;
  staff_id: string;
  bbox: BBox | null;
  confidence: number | null;
}

export interface ScoreEvent {
  kind: EventKind;
  voice: number;
  pitch: string | null;
  duration_beats: string | null;
  bbox: BBox | null;
  confidence: number | null;
  ir_handle: string | null;
}

export interface TimeSignature {
  beats: number;
  beat_type: number;
}

export interface Measure {
  number: number;
  events: ScoreEvent[];
  time_signature: TimeSignature | null;
}

export interface Staff {
  id: string;
  measures: Measure[];
}

export interface Part {
  id: string;
  staves: Staff[];
}

export interface ScoreIR {
  parts: Part[];
}

export interface EventRef {
  kind: EventKind;
  ir_handle: string | null;
  bbox: BBox | null;
  confidence: number | null;
}

export interface AnchorEntry {
  anchor: Anchor;
  event: EventRef;
}

export interface AnchorIndex {
  entries: AnchorEntry[];
}

export interface Provenance {
  omr_engine: string;
  model_version: string | null;
  rules_version: string | null;
  source_image_hash: string | null;
  created_at: string | null;
}

export interface ScoreDocument {
  id: string;
  score: ScoreIR;
  anchors: AnchorIndex;
  provenance: Provenance;
}

export type Severity = "info" | "warning" | "error";

export interface Finding {
  id: number;
  rule_id: string;
  severity: Severity;
  message: string;
  suggested_fix: string | null;
  anchor: Anchor;
}

export interface EditEvent {
  id: string;
  session_id: string;
  seq: number;
  op: string;
  author: string;
  anchor: Anchor;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export interface EditEventCreate {
  op: string;
  anchor: Anchor;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

export type UserRole = "transcriptor" | "investigador";

export interface UserProfile {
  id: string;
  username: string;
  role: UserRole;
  active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface TranscribeResponse {
  session_id: string;
  document_id: string;
  omr_engine: string;
  findings_count: number;
}

export interface SessionDetail {
  session_id: string;
  document_id: string;
  omr_engine: string;
  document: ScoreDocument;
  findings: Finding[];
  edits: EditEvent[];
}
