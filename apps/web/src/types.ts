/**
 * Tipos TypeScript del contrato API v1 de Cadenza.
 * Generado automáticamente a partir de docs/api/openapi.json (OpenAPI 3.1 / FastAPI).
 * Ejecutar: uv run python scripts/generate_openapi_and_types.py para regenerar.
 */

// --- Primitivos y tipos base del dominio ---
export type BBox = [number, number, number, number];
export type EventKind = "note" | "rest" | "clef" | "key" | "time";
export type Severity = "info" | "warning" | "error";
export type UserRole = "transcriptor" | "investigador";

/**
 * Entrada individual en el mapa de anclas del ScoreDocument.
 */
export interface AnchorEntryPayload {
  anchor: AnchorPayload;
  event: EventRefPayload;
}

/**
 * Índice determinista de anclas del documento o estado materializado.
 */
export interface AnchorIndexPayload {
  /** Lista ordenada de asociaciones ancla-evento */
  entries?: AnchorEntryPayload[];
}

/**
 * Ancla de evento en formato primitivo (contrato compartido del dominio).
 * 
 * El ancla es posicional y se interpreta respecto al estado `at_seq`
 * correspondiente: estado 0 para el documento crudo, estado `seq - 1`
 * (`base_seq`) para una edición, estado `at_seq` para un hallazgo (ADR-0011).
 */
export interface AnchorPayload {
  part: number;
  staff: number;
  measure: number;
  voice: number;
  event_index: number;
  staff_id: string;
  bbox: BBox | null;
  confidence: number | null;
}

/**
 * Payload para cambio de contraseña por el propio usuario (ADR-0012, #46).
 */
export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

/**
 * Clave musical (p. ej. Sol, Fa, Do).
 */
export interface ClefPayload {
  /** Símbolo de clave ('G', 'F', 'C') */
  sign: string;
  /** Línea del pentagrama en la que se ubica la clave */
  line?: number;
  /** Desplazamiento de octava (+1, -1, 0) */
  octave_change?: number;
}

/**
 * Payload opcional para descartar un hallazgo como falso positivo (#36).
 */
export interface DismissFindingRequest {
  reason?: string | null;
}

/**
 * Payload de una corrección humana (el servidor asigna id, seq y fecha).
 * 
 * Exige `base_seq`, que identifica el estado sobre el cual se construyó la
 * edición (ADR-0011). Si `base_seq` no coincide con el último `seq` de la sesión,
 * el servidor responde HTTP 409 Conflict y no persiste nada. El servidor nunca
 * reintenta con otro `seq` para no alterar el evento al que apunta el ancla.
 * 
 * El ancla `anchor` es posicional y se interpreta estrictamente respecto al
 * estado base declarado (`base_seq`, ADR-0011).
 */
export interface EditEventCreate {
  /** Número de secuencia del estado sobre el que se preparó la edición (ADR-0011) */
  base_seq: number;
  op: EditOp | string;
  anchor: AnchorPayload;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

export interface EditEventRead {
  id: string;
  session_id: string;
  seq: number;
  op: EditOp | string;
  author: string;
  anchor: AnchorPayload;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reverts_edit_id?: string | null;
  created_at: string;
}

/**
 * Operaciones de corrección admitidas sobre un evento anclado.
 * 
 * Esquemas de payload (atributos ``before`` y ``after`` en `EditEvent`):
 * 
 * 1. `SET_PITCH` ("SetPitch"):
 *    - Modifica la altura absoluta de una nota.
 *    - ``before``: ``{"pitch": str}`` (p. ej. ``{"pitch": "C4"}``).
 *    - ``after``: ``{"pitch": str}`` (p. ej. ``{"pitch": "D4"}``).
 * 
 * 2. `SET_DURATION` ("SetDuration"):
 *    - Modifica la duración en tiempos (beats) de un evento musical.
 *    - ``before``: ``{"duration_beats": Fraction | int | float | str}``.
 *    - ``after``: ``{"duration_beats": Fraction | int | float | str}``.
 * 
 * 3. `SET_ACCIDENTAL` ("SetAccidental"):
 *    - Modifica la alteración de una nota conservando su nombre de nota y octava.
 *    - ``before``: ``{"accidental": str | None}`` (p. ej. ``{"accidental": ""}``).
 *    - ``after``: ``{"accidental": str | None}``
 *      (p. ej. ``"#"``, ``"b"``, ``"natural"``, ``"##"``, ``"bb"``).
 * 
 * 4. `INSERT_EVENT` ("InsertEvent"):
 *    - Inserta un nuevo evento musical antes de la posición anclada.
 *    - ``before``: ``None``.
 *    - ``after``: ``{"kind": str, "pitch": str | None, "duration_beats": Fraction | str, ...}``.
 * 
 * 5. `DELETE_EVENT` ("DeleteEvent"):
 *    - Elimina el evento musical anclado en la voz del compás.
 *    - ``before``: snapshot del evento previo.
 *    - ``after``: ``None``.
 * 
 * 6. `SET_CLEF` ("SetClef"):
 *    - Modifica la clave musical del compás al que apunta el ancla.
 *    - ``before``: snapshot de clave previa o ``None``.
 *    - ``after``: ``{"clef": dict | str | Clef}`` o primitivo ``{"sign": str, "line": int}``.
 * 
 * 7. `SET_KEY` ("SetKey"):
 *    - Modifica la armadura de clave del compás al que apunta el ancla.
 *    - ``before``: snapshot de armadura previa o ``None``.
 *    - ``after``: ``{"key_signature": dict | KeySignature}`` o primitivo ``{"fifths": int}``.
 */
export type EditOp = "SetPitch" | "SetDuration" | "SetAccidental" | "InsertEvent" | "DeleteEvent" | "SetClef" | "SetKey";

/**
 * Payload para registrar métricas de esfuerzo de corrección (#13).
 */
export interface EffortMetricsCreate {
  /** Duración total de corrección en ms */
  duration_ms: number;
  /** Tiempo hasta la primera edición en ms */
  time_to_first_edit_ms?: number | null;
  /** Intervenciones por número de compás */
  interventions?: Record<string, number>;
}

/**
 * Métricas de esfuerzo persistidas para una sesión (#13).
 */
export interface EffortMetricsRead {
  id: string;
  session_id: string;
  duration_ms: number;
  time_to_first_edit_ms: number | null;
  interventions: Record<string, number>;
  created_at: string;
}

/**
 * Estructura uniforme de mensaje de error HTTP de la API.
 */
export interface ErrorDetail {
  /** Descripción del error o detalle de validación */
  detail: unknown;
}

/**
 * Referencia mínima al evento del ScoreIR asociado a un ancla.
 */
export interface EventRefPayload {
  /** Tipo de evento musical ('note', 'rest', 'clef', 'key', 'time') */
  kind: EventKind;
  /** Identificador interno del manejador IR */
  ir_handle?: string | null;
  /** Coordenadas normalizadas de bounding box */
  bbox?: BBox | null;
  /** Confianza asignada al evento */
  confidence?: number | null;
}

/**
 * Respuesta tras finalizar una sesión de transcripción (ADR-0014, #34).
 */
export interface FinalizeResponse {
  session_id: string;
  status: string;
  final_seq: number;
  findings: FindingRead[];
}

export interface FindingRead {
  id: number;
  rule_id: string;
  severity: Severity;
  message: string;
  suggested_fix: string | null;
  anchor: AnchorPayload;
  at_seq?: number;
  status?: string;
  dismissed_at?: string | null;
  dismissed_by?: string | null;
  dismissal_reason?: string | null;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

/**
 * Armadura de clave expresada en número de quintas respecto a Do mayor.
 */
export interface KeySignaturePayload {
  /** Número de alteraciones en quintas (-7 bemoles a +7 sostenidos) */
  fifths: number;
  /** Modo armónico opcional ('major', 'minor') */
  mode?: string | null;
}

/**
 * Compás que agrupa eventos musicales y metadatos estructurales.
 */
export interface MeasurePayload {
  /** Número de compás (1-indexed) */
  number: number;
  /** Secuencia de eventos musicales */
  events: ScoreEventPayload[];
  /** Signatura de compás */
  time_signature?: TimeSignaturePayload | null;
  /** Clave musical activa en el compás */
  clef?: ClefPayload | null;
  /** Armadura de clave activa */
  key_signature?: KeySignaturePayload | null;
}

/**
 * Parte instrumental o vocal que agrupa uno o varios pentagramas.
 */
export interface PartPayload {
  /** Identificador de la parte (p. ej. 'part-0') */
  id: string;
  /** Lista de pentagramas de la parte */
  staves: StaffPayload[];
}

/**
 * Trazabilidad y procedencia de la inferencia OMR y validación.
 */
export interface ProvenancePayload {
  /** Nombre del motor OMR utilizado ('fake', 'homr') */
  omr_engine: string;
  /** Versión del modelo OMR */
  model_version?: string | null;
  /** Versión del catálogo de reglas */
  rules_version?: string | null;
  /** Hash SHA-256 de la imagen de origen */
  source_image_hash?: string | null;
  /** Marca de tiempo ISO-8601 de creación */
  created_at?: string | null;
  /** Dispositivo de cómputo efectivo ('cpu', 'cuda') */
  device?: string | null;
  /** Metadatos y configuración de la etapa de preprocesado aplicada */
  preprocessing?: Record<string, unknown> | null;
}

/**
 * Respuesta tras reabrir una sesión finalizada (ADR-0014, #34).
 */
export interface ReopenResponse {
  session_id: string;
  status: string;
  current_seq: number;
}

/**
 * Respuesta tras revalidación de la partitura (ADR-0011, ADR-0013, #11, #48).
 * 
 * Devuelve el `current_seq` de la sesión y la lista de hallazgos evaluados,
 * cada uno con su `at_seq` correspondiente.
 */
export interface RevalidateResponse {
  session_id: string;
  current_seq: number;
  findings: FindingRead[];
}

/**
 * Documento musical integral: ScoreIR + Índice de anclas + Provenance.
 */
export interface ScoreDocumentPayload {
  /** Identificador único del documento */
  id: string;
  /** Árbol simbólico ScoreIR */
  score: ScoreIRPayload;
  /** Índice de anclas de la partitura */
  anchors: AnchorIndexPayload;
  /** Metadatos de procedencia del documento */
  provenance: ProvenancePayload;
}

/**
 * Evento musical individual en un compás (nota, silencio, etc.).
 */
export interface ScoreEventPayload {
  /** Tipo de evento ('note', 'rest', etc.) */
  kind: EventKind;
  /** Índice de voz dentro del pentagrama */
  voice: number;
  /** Altura en notación científica (p. ej. 'C4', 'F#5') */
  pitch: string | null;
  /** Duración exacta en pulsos como fracción ('1/4', '1', '3/8') */
  duration_beats: string | null;
  /** Estado de ligadura ('start', 'continue', 'stop') */
  tie?: string | null;
  /** Indica si la nota pertenece a un acorde simultáneo */
  is_chord?: boolean;
  /** Bounding box normalizado */
  bbox: BBox | null;
  /** Puntuación de confianza del reconocimiento */
  confidence: number | null;
  /** Manejador de referencia interna */
  ir_handle: string | null;
}

/**
 * Representación intermedia simbólica normalizada de la partitura (ScoreIR).
 */
export interface ScoreIRPayload {
  /** Partes que componen la partitura */
  parts: PartPayload[];
}

/**
 * Documento persistido + findings + correcciones de una sesión (HITL).
 * 
 * `current_seq` indica el estado de secuencia de la partitura actual (`0` para crudo,
 * `n` para `n` ediciones). `current_score` es el ScoreIR materializado y
 * `anchor_index` contiene el índice de anclas correspondiente al estado actual,
 * con `bbox` y `confidence` heredadas del documento original (ADR-0011).
 */
export interface SessionDetailRead {
  session_id: string;
  document_id: string;
  omr_engine: string;
  document: ScoreDocumentPayload;
  findings: FindingRead[];
  edits: EditEventRead[];
  current_score?: ScoreIRPayload | null;
  current_seq?: number;
  anchor_index?: AnchorIndexPayload | null;
  image_artifact?: string | null;
  model_version?: string | null;
  status?: string;
  condition?: string;
  test_score_id?: string | null;
  owner_id?: string | null;
}

/**
 * Resumen ligero de una sesión para listados (sin el documento JSONB) (#27).
 */
export interface SessionSummaryRead {
  session_id: string;
  document_id: string;
  omr_engine: string;
  model_version?: string | null;
  status: string;
  created_at: string;
  findings_count?: number;
  edits_count?: number;
  condition?: string;
  test_score_id?: string | null;
  owner_id?: string | null;
}

/**
 * Pentagrama que agrupa compases en una parte.
 */
export interface StaffPayload {
  /** Identificador único del pentagrama (p. ej. 'part-0-staff-0') */
  id: string;
  /** Lista de compases del pentagrama */
  measures: MeasurePayload[];
}

/**
 * Respuesta con mensaje de estado de la operación.
 */
export interface StatusResponse {
  status: string;
  message?: string | null;
}

/**
 * Signatura de compás (métrica) de un compás.
 */
export interface TimeSignaturePayload {
  /** Número de pulsos por compás */
  beats: number;
  /** Figura musical que representa un pulso */
  beat_type: number;
}

/**
 * Respuesta de autenticación con token de acceso Bearer (OAuth2).
 */
export interface TokenResponse {
  access_token: string;
  token_type?: string;
}

export interface TranscribeResponse {
  session_id: string;
  document_id: string;
  omr_engine: string;
  findings_count: number;
  condition?: string;
  test_score_id?: string | null;
}

/**
 * Payload opcional para deshacer una edición con validación de concurrencia (#35, #48).
 */
export interface UndoRequest {
  /** Número de secuencia base esperado. Si se especifica y no coincide con el estado actual, responde 409. */
  base_seq?: number | null;
}

/**
 * Respuesta tras deshacer una edición en el servidor (ADR-0007, ADR-0011, #35, #48).
 */
export interface UndoResponse {
  session_id: string;
  current_seq: number;
  undone_edit_id: string;
  current_score: ScoreIRPayload;
  anchor_index?: AnchorIndexPayload | null;
  compensatory_edit_id?: string | null;
  compensatory_edit?: EditEventRead | null;
}

/**
 * Payload para dar de alta una cuenta (ADR-0012, #46).
 */
export interface UserCreate {
  username: string;
  password: string;
  role: UserRole;
}

/**
 * Perfil público de un usuario autenticado (ADR-0012).
 */
export interface UserRead {
  id: string;
  username: string;
  role: UserRole;
  active: boolean;
  created_at?: string | null;
}

/**
 * Payload para modificar rol, estado o restablecer contraseña (ADR-0012, #46).
 */
export interface UserUpdate {
  role?: string | null;
  active?: boolean | null;
  password?: string | null;
}

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

/**
 * Versión de la API y del servicio.
 */
export interface VersionResponse {
  /** Versión del contrato API v1 */
  api_version?: string;
  /** Versión de la aplicación Cadenza */
  app_version?: string;
}

// --- Alias ergonómicos de compatibilidad para el Frontend ---
export type Anchor = AnchorPayload;
export type ScoreEvent = ScoreEventPayload;
export type TimeSignature = TimeSignaturePayload;
export type Clef = ClefPayload;
export type KeySignature = KeySignaturePayload;
export type Measure = MeasurePayload;
export type Staff = StaffPayload;
export type Part = PartPayload;
export type ScoreIR = ScoreIRPayload;
export type EventRef = EventRefPayload;
export type AnchorEntry = AnchorEntryPayload;
export type AnchorIndex = AnchorIndexPayload;
export type Provenance = ProvenancePayload;
export type ScoreDocument = ScoreDocumentPayload;
export type Finding = FindingRead;
export type EditEvent = EditEventRead;
export type SessionDetail = SessionDetailRead;
export type SessionSummary = SessionSummaryRead;
export type UserProfile = UserRead;
