import { useId, useLayoutEffect, useRef, useState, type MutableRefObject } from "react";
import { PixelIcon, type PixelIconName } from "../../components/PixelIcon";
import type { AnchorPayload, ScoreIRPayload } from "../../types";
import {
  accidentalOf,
  activeFifths,
  attributeRange,
  CLEFS,
  drawnDuration,
  figureOf,
  FIGURES,
  isGap,
  keyLabel,
  eventName,
  planCommand,
  rangeName,
  type Accidental,
  type EditCommand,
  type EditTarget,
  type PlannedCommand,
} from "./edits";
import type { Editor, EditorRequest, EditorStatus } from "./editor";
import { describeEdit, hasCompleteBefore, placeOf } from "./history";
import {
  ARTICULATIONS,
  DYNAMICS,
  dynamicAt,
  marksHolder,
  noteMarksOf,
  spanName,
  spansAt,
  type DynamicValue,
  type SpanKind,
} from "./markEdits";
import { timeRange, tupletPressed, type TupletScope } from "./meterEdits";
import { tieArrives, tieLeaves } from "./tieEdits";
import {
  KeyCap,
  SelectionAnnouncement,
  SelectionKeys,
  SelectionReadout,
  SelectionSteps,
} from "./SelectionBar";
import { selectionReady, type SelectionControls } from "./selectionControls";
import { SuggestionList, type SuggestionActions } from "./SuggestionList";
import type { SuggestionItem } from "./suggestions";
import { TimePicker } from "./TimePicker";
import type { EditEventRead, FindingRead } from "../../types";

/** Pestañas de la barra de corrección (#341): lo de la nota, lo del compás y las marcas. */
export type ToolTab = "note" | "measure" | "marks";

const TOOL_TABS: readonly { id: ToolTab; label: string }[] = [
  { id: "note", label: "Nota" },
  { id: "measure", label: "Compás" },
  { id: "marks", label: "Marcas" },
];

interface EditBarProps {
  editor: Editor;
  /** Si se ofrecen los controles: la sesión es de quien la ve y no está finalizada. */
  editable: boolean;
  /**
   * Si se ofrecen deshacer y rehacer (ADR-0034): como `editable`, también cuando la partitura no
   * se puede dibujar, para deshacer la edición que la dejó así.
   */
  undoable: boolean;
  /** Evento elegido en el estado que se muestra, o null si no hay ninguno que corregir. */
  target: EditTarget | null;
  /** Estado que se muestra: el del evento elegido (su armadura, su clave, su compás). */
  score: ScoreIRPayload | null;
  /** `seq` del estado que se muestra. */
  seq: number;
  multiStaff: boolean;
  /** Identificador de la leyenda de teclas, que también describe la partitura. */
  keysId: string;
  /** Lleva el foco a la partitura; false si ahora no lo puede tomar. */
  focusScore?: () => boolean;
  /**
   * Control que tenía el foco en la barra a la que esta sustituye (la partitura pasó a dibujarse o
   * dejó de poder dibujarse, y la barra se montó en otro sitio): esta se lo devuelve.
   */
  focusMemoryRef?: MutableRefObject<string | null>;
  /**
   * Sugerencias de la capa para la nota elegida (#258), con lo que se puede hacer con ellas y
   * cómo se nombra su posible error. Sin ninguna, la barra no las menciona.
   */
  suggestions?: {
    items: readonly SuggestionItem[];
    labelOf: (finding: FindingRead) => string;
    actions?: SuggestionActions;
  };
  /** Pestaña de herramientas que se ve (#341); sin ella, la barra recuerda la suya. */
  tab?: ToolTab;
  onTab?: (tab: ToolTab) => void;
  /** Quién recibe las órdenes de los botones: la vista, que lleva el modo «Escribir» (#350). */
  onCommand?: (command: EditCommand, target: EditTarget | null) => void;
  /** El modo «Escribir» (#350): la figura con que se escribe, o null fuera de él. */
  writing?: { figure: number; dotted: boolean } | null;
  onToggleWriting?: () => void;
  /**
   * La selección de notas de la partitura (#363): sus pasos van en la primera fila, la nota
   * elegida en la barra de estado y su leyenda con la de la corrección, tras «Atajos».
   */
  selection?: SelectionControls;
  /** Si se ven las leyendas de teclas (#341); sin `onToggleKeys`, siempre se ven. */
  keysShown?: boolean;
  onToggleKeys?: () => void;
}

const PITCH: { command: PlannedCommand; label: string; word: string; icon: PixelIconName }[] = [
  {
    command: { kind: "step", direction: -1 },
    label: "Bajar un paso",
    word: "Paso",
    icon: "arrow-down",
  },
  {
    command: { kind: "step", direction: 1 },
    label: "Subir un paso",
    word: "Paso",
    icon: "arrow-up",
  },
  {
    command: { kind: "octave", direction: -1 },
    label: "Bajar una octava",
    word: "Octava",
    icon: "octave-down",
  },
  {
    command: { kind: "octave", direction: 1 },
    label: "Subir una octava",
    word: "Octava",
    icon: "octave-up",
  },
];

const ACCIDENTAL_BUTTONS: { accidental: Accidental; label: string; icon: PixelIconName }[] = [
  { accidental: "bb", label: "Doble bemol", icon: "accidental-double-flat" },
  { accidental: "b", label: "Bemol", icon: "accidental-flat" },
  { accidental: "", label: "Becuadro", icon: "accidental-natural" },
  { accidental: "#", label: "Sostenido", icon: "accidental-sharp" },
  { accidental: "##", label: "Doble sostenido", icon: "accidental-double-sharp" },
];

const FIGURE_ICONS: PixelIconName[] = [
  "figure-sixty-fourth",
  "figure-thirty-second",
  "figure-sixteenth",
  "figure-eighth",
  "figure-quarter",
  "figure-half",
  "figure-whole",
];

/**
 * Insertar antes del evento elegido y borrarlo (ADR-0033). «Nota» y «Silencio» se ven siempre: el
 * más no dice qué se inserta. En una barra estrecha, «Borrar» queda en su aspa, para que los tres
 * quepan en una fila a 390 px.
 */
const STRUCTURE: {
  command: PlannedCommand;
  label: string;
  text?: string;
  word?: string;
  icon: PixelIconName;
}[] = [
  {
    command: { kind: "insert", rest: false },
    label: "Insertar una nota antes",
    text: "Nota",
    icon: "plus",
  },
  {
    command: { kind: "insert", rest: true },
    label: "Insertar un silencio antes",
    text: "Silencio",
    icon: "plus",
  },
  { command: { kind: "delete" }, label: "Borrar", word: "Borrar", icon: "cross" },
];

const ARTICULATION_ICONS: Record<string, PixelIconName> = {
  staccato: "mark-staccato",
  staccatissimo: "mark-staccatissimo",
  accent: "mark-accent",
  marcato: "mark-marcato",
  tenuto: "mark-tenuto",
};

/** Ligaduras y reguladores que se crean desde el inicio marcado hasta el evento elegido. */
const SPANS: { span: SpanKind; label: string; text: string; icon: PixelIconName }[] = [
  { span: "slur", label: "Ligadura de expresión hasta aquí", text: "Ligadura", icon: "mark-slur" },
  { span: "crescendo", label: "Crescendo hasta aquí", text: "Cresc.", icon: "mark-crescendo" },
  {
    span: "diminuendo",
    label: "Diminuendo hasta aquí",
    text: "Dim.",
    icon: "mark-diminuendo",
  },
];

/**
 * Tresillos (#241, ADR-0048): a tres figuras desde la elegida (o el de su grupo), a todo su compás
 * o al tramo desde el inicio marcado. Pulsado si ya lo llevan: pulsarlo lo quita. Textos breves,
 * para que el grupo quepa en una fila a 390 px; el nombre accesible y el `title` lo dicen entero.
 */
const TUPLETS: { scope: TupletScope; label: string; text: string }[] = [
  { scope: "group", label: "Tresillo en tres figuras desde la elegida", text: "Tres" },
  { scope: "measure", label: "Tresillo en todo el compás", text: "Compás" },
  { scope: "range", label: "Tramo: tresillo desde el inicio hasta la elegida", text: "Tramo" },
];

/** Armaduras que se ofrecen, de siete bemoles a siete sostenidos. */
const KEYS = Array.from({ length: 15 }, (_unused, index) => index - 7);

/** Cómo se reconoce un control de la barra en otra barra: su nombre accesible o su texto. */
const focusKey = (element: HTMLElement) =>
  element.getAttribute("aria-label") ?? element.textContent;

/** Un texto igual al anterior no se volvería a leer: un espacio duro al final lo distingue. */
const HARD_SPACE = String.fromCharCode(0xa0);
const distinct = (message: string, nonce: number) =>
  nonce % 2 === 1 ? `${message}${HARD_SPACE}` : message;

/**
 * Un 422 (u otro rechazo) no cambió nada. Al deshacer, si la edición no guardó su estado previo
 * (anterior a ADR-0017), el servidor no la puede deshacer sin alterar la partitura: se dice así.
 */
function rejection(request: EditorRequest, where: string): string {
  switch (request.kind) {
    case "edit":
      return `El servidor no aceptó el cambio (${where}): no se guardó nada.`;
    case "redo":
      return `El servidor no aceptó rehacer (${where}): no se guardó nada.`;
    case "undo":
      return hasCompleteBefore(request.edit)
        ? `El servidor no aceptó deshacer (${where}): no se cambió nada.`
        : `No se puede deshacer la edición ${String(request.edit.seq)} (${where}): es de antes de que el servidor guardara el estado previo de cada edición, y deshacerla alteraría la partitura. No se cambió nada.`;
  }
}

/** Sin respuesta, o con una que no lo confirma, no se sabe si la orden se hizo. */
function uncertainty(request: EditorRequest, where: string, reason: "silent" | "server"): string {
  const check = "Recarga la sesión para comprobarlo.";
  if (request.kind === "edit") {
    return reason === "silent"
      ? `No hubo respuesta del servidor: puede que el cambio (${where}) no se guardara. ${check}`
      : `El servidor no confirmó el cambio (${where}): puede que no se guardara. ${check}`;
  }
  const [maybe, done] =
    request.kind === "undo" ? ["deshiciera", "deshizo"] : ["rehiciera", "rehízo"];
  return reason === "silent"
    ? `No hubo respuesta del servidor: puede que no se ${maybe} (${where}). ${check}`
    : `El servidor no confirmó si se ${done} (${where}). ${check}`;
}

/** Cómo se dice lo que pasa con cada clase de orden: corregir, deshacer o rehacer. */
const WORDS = {
  edit: { saving: "Guardando…", done: "Guardado", notDone: "No se guardó", it: "guardarlo" },
  undo: { saving: "Deshaciendo…", done: "Deshecho", notDone: "No se deshizo", it: "deshacerlo" },
  redo: { saving: "Rehaciendo…", done: "Rehecho", notDone: "No se rehízo", it: "rehacerlo" },
} as const;

/** Lo que se dice tras una orden, y si hace falta recargar para seguir. */
function feedback(
  status: EditorStatus,
  multiStaff: boolean,
  score: ScoreIRPayload | null,
  retry: Editor["retry"],
): { text: string; reload: boolean } {
  const what = (request: EditorRequest) =>
    `${request.change} (${placeOf(request, multiStaff, score)})`;
  const inline = (request: EditorRequest) =>
    `${request.change}, ${placeOf(request, multiStaff, score)}`;
  switch (status.kind) {
    case "idle":
      return { text: "", reload: false };
    case "saving":
      return { text: WORDS[status.request.kind].saving, reload: false };
    case "saved": {
      const { request } = status;
      // Deshacer y rehacer dicen dónde: lo que cambia puede no ser la nota elegida.
      if (request.kind !== "edit") {
        return { text: `${WORDS[request.kind].done}: ${what(request)}.`, reload: false };
      }
      const { change, notice } = request;
      return { text: `Guardado: ${change}.${notice ? ` ${notice}` : ""}`, reload: false };
    }
    case "refused":
    case "noted":
      return { text: distinct(status.message, status.nonce), reload: false };
    case "conflict": {
      const { request } = status;
      const words = WORDS[request.kind];
      const base = `${words.notDone}: ${what(request)}. La sesión cambió en otra pestaña o dispositivo antes de ${words.it}; ya ves su estado actual.`;
      // Una sugerencia no se vuelve a aplicar: sobre el estado nuevo es antigua (#258).
      if (request.kind === "edit" && request.suggestion) {
        return {
          text: `${base} La sugerencia ya es antigua: revalida para aplicarla.`,
          reload: false,
        };
      }
      if (request.kind !== "edit" || !retry || retry.plan.kind === "edit") {
        return { text: base, reload: false };
      }
      // Sin nada que volver a aplicar, se dice por qué.
      const reason = retry.anchor
        ? retry.plan.message
        : "La nota que elegiste ya no está en el mismo sitio: elígela de nuevo si sigue haciendo falta.";
      return { text: `${base} ${reason}`, reload: false };
    }
    case "closed":
      return {
        text: `${WORDS[status.request.kind].notDone}: ${what(status.request)}. La sesión está finalizada y ya no admite correcciones.`,
        reload: false,
      };
    case "outdated": {
      const words = WORDS[status.request.kind];
      return {
        text: `${words.notDone}: ${what(status.request)}. La sesión cambió antes de ${words.it} y no se pudo cargar su estado actual: recárgala para seguir.`,
        reload: true,
      };
    }
    case "rejected":
      return { text: rejection(status.request, inline(status.request)), reload: false };
    case "stale-suggestion":
      return {
        text: `No se aplicó la sugerencia (${inline(status.request)}): ya no es de la última validación, porque se revalidó o se respondió en otra pestaña o dispositivo. Revalida para tener las sugerencias al día.`,
        reload: false,
      };
    case "forbidden":
      return {
        text: `${WORDS[status.request.kind].notDone}: solo la persona que hizo la transcripción puede corregirla.`,
        reload: false,
      };
    case "missing":
      return {
        text: `${WORDS[status.request.kind].notDone}: la sesión ya no existe o no tienes acceso a ella.`,
        reload: false,
      };
    case "unknown":
      return {
        text: uncertainty(status.request, inline(status.request), status.reason),
        reload: true,
      };
    case "unsynced": {
      const { kind } = status.request;
      const done =
        kind === "edit" ? "Se guardó el cambio" : kind === "undo" ? "Se deshizo" : "Se rehízo";
      return {
        text: `${done} (${inline(status.request)}), pero no se pudo cargar la partitura nueva. Recarga la sesión para seguir corrigiendo.`,
        reload: true,
      };
    }
    // El botón sigue mientras recarga, inactivo: si desapareciera, se perdería el foco.
    case "reloading":
      return { text: "Recargando la sesión…", reload: true };
    case "reloaded":
      return { text: "Sesión recargada.", reload: false };
    case "reload-failed":
      return {
        text: "No se pudo recargar la sesión. Comprueba la conexión e inténtalo de nuevo.",
        reload: true,
      };
  }
}

/**
 * En un hueco de una voz (ADR-0058), los mismos tres botones escriben una nota en él, lo hacen un
 * silencio que se ve y lo borran: un hueco no tiene figura dibujada, así que antes de él y en él
 * son el mismo sitio.
 */
const GAP_STRUCTURE: typeof STRUCTURE = [
  {
    command: { kind: "insert", rest: false },
    label: "Escribir una nota en el hueco",
    text: "Nota",
    icon: "plus",
  },
  {
    command: { kind: "insert", rest: true },
    label: "Hacer el hueco un silencio que se ve",
    text: "Silencio",
    icon: "plus",
  },
  { command: { kind: "delete" }, label: "Borrar el hueco", word: "Borrar", icon: "cross" },
];

/**
 * Qué indicar en la barra de estado según lo elegido. Sin nada elegido lo dice la selección («Elige
 * una nota o un silencio…»), una sola vez (#363).
 */
function hint(target: EditTarget | null): string | null {
  if (!target) return null;
  if (isGap(target.event)) {
    return "Un hueco de la voz no se dibuja: escribe una nota en él, hazlo un silencio o bórralo para que lo que sigue se adelante.";
  }
  if (target.event.kind !== "note") return "Un silencio no tiene altura ni alteración.";
  if (target.chord) {
    return "En un acorde, la altura y la alteración son de cada nota y la figura, de todas a la vez; al borrar su primera nota, la siguiente lleva la figura y las marcas.";
  }
  return null;
}

interface CommandButtonProps {
  command: PlannedCommand;
  label: string;
  icon?: PixelIconName;
  /** Palabra visible junto al icono; en una barra estrecha queda solo el icono. */
  word?: string;
  /** Texto que se ve siempre, también en una barra estrecha. */
  text?: string;
  /** Si es el valor que ya tiene el evento: un conmutador pulsado. */
  pressed?: boolean;
  target: EditTarget | null;
  score: ScoreIRPayload | null;
  /** Inicio marcado para una ligadura o un regulador, en el estado que se ve. */
  origin?: AnchorPayload | null;
  blocked: boolean;
  onRun: (command: PlannedCommand) => void;
  /**
   * Si el botón no envía ninguna edición (en el modo «Escribir», la figura elige con qué se
   * escribe, #350): siempre se puede pulsar.
   */
  free?: boolean;
}

/** Botón de una orden: inactivo si ahora no se puede; pulsado si es el valor que ya tiene. */
function CommandButton({
  command,
  label,
  icon,
  word,
  text,
  pressed,
  target,
  score,
  origin = null,
  blocked,
  onRun,
  free = false,
}: CommandButtonProps) {
  const plan = planCommand(command, target, score, origin);
  // El valor que ya tiene no está inactivo: está pulsado, y pulsarlo lo dice. Un tresillo o una
  // ligadura de prolongación que no se pueden ahí tampoco: pulsarlo dice por qué (falta el
  // inicio, una figura con puntillo, lo siguiente no es la misma nota…).
  const disabled =
    !free &&
    (blocked ||
      (plan.kind === "refused" &&
        plan.reason !== "same" &&
        plan.reason !== "meter" &&
        plan.reason !== "tie"));
  return (
    <button
      type="button"
      className="editor__button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      aria-disabled={disabled}
      onClick={() => {
        if (!disabled) onRun(command);
      }}
    >
      {icon && <PixelIcon name={icon} />}
      {word && <span className="editor__word">{word}</span>}
      {text && <span className="editor__text">{text}</span>}
    </button>
  );
}

interface KeyPickerProps {
  /** Rótulo del grupo, que nombra el desplegable. */
  labelId: string;
  target: EditTarget | null;
  score: ScoreIRPayload | null;
  blocked: boolean;
  onRun: (command: PlannedCommand) => void;
}

/**
 * Armadura del compás elegido: un desplegable con las quince y «Cambiar», que envía la elegida.
 * El desplegable solo propone: con el teclado, cada flecha cambia su valor, y cada valor no es
 * una edición. Propone la que rige el compás elegido y vuelve a ella cuando cambia el compás o
 * su armadura, sin montarse de nuevo: el foco se queda en «Cambiar» tras guardar.
 */
function KeyPicker({ labelId, target, score, blocked, onRun }: KeyPickerProps) {
  const current = target && score ? activeFifths(score, target.anchor) : 0;
  const origin = target
    ? `${String(target.anchor.part)}:${String(target.anchor.staff)}:${String(target.anchor.measure)}:${String(current)}`
    : null;
  const [draft, setDraft] = useState<{ origin: string | null; fifths: number }>({
    origin,
    fifths: current,
  });
  // Lo propuesto vale para un compás y su armadura: al pasar a otro (o al guardarla) se olvida,
  // también si después se vuelve al mismo compás.
  if (draft.origin !== origin) setDraft({ origin, fifths: current });
  const fifths = draft.origin === origin ? draft.fifths : current;
  const command: PlannedCommand = { kind: "key", fifths };
  const plan = planCommand(command, target, score);
  const disabled = blocked || plan.kind === "refused";
  return (
    <div className="editor__buttons">
      <select
        className="editor__select"
        aria-labelledby={labelId}
        value={String(fifths)}
        disabled={!target}
        onChange={(event) => {
          setDraft({ origin, fifths: Number(event.target.value) });
        }}
      >
        {KEYS.map((key) => (
          <option key={key} value={String(key)}>
            {keyLabel(key)}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="editor__button"
        aria-label="Cambiar armadura"
        title="Cambiar armadura"
        aria-disabled={disabled}
        onClick={() => {
          if (!disabled) onRun(command);
        }}
      >
        <span className="editor__text">Cambiar</span>
      </button>
    </div>
  );
}

/**
 * Dinámica en la posición del evento elegido (#214, ADR-0039): un desplegable con las doce y «Sin
 * dinámica», y un botón que la pone o la quita. Como el de la armadura, el desplegable solo
 * propone: propone la que tiene esa posición y vuelve a ella al cambiar de evento o de dinámica.
 */
function DynamicPicker({ labelId, target, score, blocked, onRun }: KeyPickerProps) {
  const current = target && score ? dynamicAt(score, target.anchor) : null;
  const origin = target
    ? `${String(target.anchor.part)}:${String(target.anchor.staff)}:${String(target.anchor.measure)}:${String(target.anchor.voice)}:${String(target.anchor.event_index)}:${String(current)}`
    : null;
  const [draft, setDraft] = useState<{ origin: string | null; mark: DynamicValue | null }>({
    origin,
    mark: current,
  });
  if (draft.origin !== origin) setDraft({ origin, mark: current });
  const mark = draft.origin === origin ? draft.mark : current;
  const command: PlannedCommand = { kind: "dynamic", mark };
  const plan = planCommand(command, target, score);
  const disabled = blocked || plan.kind === "refused";
  const label = mark === null && current !== null ? "Quitar dinámica" : "Poner dinámica";
  return (
    <div className="editor__buttons">
      <select
        className="editor__select"
        aria-labelledby={labelId}
        value={mark ?? ""}
        disabled={!target}
        onChange={(event) => {
          const value = event.target.value;
          setDraft({
            origin,
            mark: DYNAMICS.find((candidate) => candidate === value) ?? null,
          });
        }}
      >
        <option value="">Sin dinámica</option>
        {DYNAMICS.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="editor__button"
        aria-label={label}
        title={label}
        aria-disabled={disabled}
        onClick={() => {
          if (!disabled) onRun(command);
        }}
      >
        <span className="editor__text">
          {mark === null && current !== null ? "Quitar" : "Poner"}
        </span>
      </button>
    </div>
  );
}

interface SpanControlsProps {
  labelId: string;
  editor: Editor;
  target: EditTarget | null;
  score: ScoreIRPayload | null;
  blocked: boolean;
  onRun: (command: PlannedCommand) => void;
}

/**
 * Ligaduras de expresión y reguladores (#214, ADR-0039): «Inicio» marca el evento elegido como
 * principio y Ligadura, Crescendo y Diminuendo crean la marca desde él hasta el evento elegido.
 * Debajo, las que pasan por el evento elegido, cada una con su botón para quitarla entera.
 */
function SpanControls({ labelId, editor, target, score, blocked, onRun }: SpanControlsProps) {
  const noteId = useId();
  const { origin, originEvent } = editor;
  const isOrigin =
    origin !== null &&
    target !== null &&
    origin.part === target.anchor.part &&
    origin.staff === target.anchor.staff &&
    origin.measure === target.anchor.measure &&
    origin.voice === target.anchor.voice &&
    origin.event_index === target.anchor.event_index;
  const spans = target && score ? spansAt(score, target.anchor) : [];
  const note =
    origin && originEvent
      ? `Inicio: ${eventName(originEvent.kind, originEvent.pitch, originEvent.duration_beats)} (compás ${String(origin.measure)}).`
      : "Elige la nota del inicio, pulsa «Inicio» y elige la del final.";
  return (
    <>
      <div className="editor__buttons">
        <button
          type="button"
          className="editor__button"
          aria-label="Inicio de la ligadura o el regulador"
          title="Inicio de la ligadura o el regulador"
          aria-pressed={isOrigin}
          aria-describedby={noteId}
          aria-disabled={blocked || !target}
          onClick={() => {
            if (!blocked && target) editor.run({ kind: "origin" }, target);
          }}
        >
          <span className="editor__text">Inicio</span>
        </button>
        {SPANS.map(({ span, label, text, icon }) => (
          <CommandButton
            key={span}
            command={{ kind: "span", span }}
            label={label}
            icon={icon}
            word={text}
            target={target}
            score={score}
            origin={origin}
            blocked={blocked}
            onRun={onRun}
          />
        ))}
      </div>
      <div className="editor__origin">
        <p className="editor__history" id={noteId}>
          {note}
        </p>
        {origin && (
          <button type="button" className="link-button" onClick={editor.clearOrigin}>
            Olvidar el inicio
          </button>
        )}
      </div>
      {spans.length > 0 && (
        <ul className="editor__spans" aria-labelledby={labelId}>
          {spans.map((info) => {
            const name = spanName(info);
            return (
              <li key={`${info.mark}-${String(info.number)}`}>
                <CommandButton
                  command={{ kind: "unspan", mark: info.mark, number: info.number }}
                  label={`Quitar ${name}`}
                  icon="cross"
                  text={`Quitar ${name}`}
                  target={target}
                  score={score}
                  blocked={blocked}
                  onRun={onRun}
                />
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

interface HistoryControlsProps {
  editor: Editor;
  multiStaff: boolean;
  score: ScoreIRPayload | null;
}

/**
 * Deshacer y rehacer (ADR-0034): no dependen de la nota elegida. Dicen qué desharían y qué
 * reharían y, sin nada, que no hay nada; Ctrl+Z y los suyos valen en toda la vista, salvo en un
 * campo de texto, y los botones lo declaran.
 */
function HistoryControls({ editor, multiStaff, score }: HistoryControlsProps) {
  const labelId = useId();
  const noteId = useId();
  const { blocked, log } = editor;
  const what = (edit: EditEventRead) =>
    `${describeEdit(edit)} (${placeOf(edit, multiStaff, score)})`;
  const note =
    !log.undo && !log.redo
      ? "Nada que deshacer ni rehacer."
      : `${log.undo ? `Deshace: ${what(log.undo)}.` : "Nada que deshacer."} ${
          log.redo ? `Rehace: ${what(log.redo)}.` : "Nada que rehacer."
        }`;
  const buttons = [
    {
      label: "Deshacer",
      icon: "undo",
      edit: log.undo,
      none: "Nada que deshacer",
      keys: "Control+Z Meta+Z",
      onRun: editor.undo,
    },
    {
      label: "Rehacer",
      icon: "redo",
      edit: log.redo,
      none: "Nada que rehacer",
      keys: "Control+Shift+Z Meta+Shift+Z Control+Y",
      onRun: editor.redo,
    },
  ] as const;
  return (
    <>
      <div className="editor__group editor__group--history" role="group" aria-labelledby={labelId}>
        <p className="label editor__label" id={labelId}>
          Deshacer y rehacer
        </p>
        <div className="editor__buttons">
          {buttons.map(({ label, icon, edit, none, keys, onRun }) => {
            const disabled = blocked || !edit;
            return (
              <button
                key={label}
                type="button"
                className="editor__button"
                aria-label={label}
                title={edit ? `${label}: ${what(edit)}` : none}
                aria-describedby={noteId}
                aria-keyshortcuts={keys}
                aria-disabled={disabled}
                onClick={() => {
                  if (!disabled) onRun();
                }}
              >
                <PixelIcon name={icon} />
                <span className="editor__text">{label}</span>
              </button>
            );
          })}
        </div>
      </div>
      {/* Qué desharía y qué reharía: en el `title` y la descripción de sus botones, no en una línea
          suelta bajo la barra (#363, enmienda de ADR-0034 §4). */}
      <p className="editor__history visually-hidden" id={noteId}>
        {note}
      </p>
    </>
  );
}

/**
 * Barra de corrección de la nota elegida (ADR-0030, ADR-0033): altura, alteración y figura;
 * el tresillo (ADR-0048); insertar antes y borrar; añadir una nota al acorde y la ligadura de
 * prolongación (ADR-0055); la clave, la armadura y el compás de su compás; y deshacer y rehacer
 * (ADR-0034).
 * Cada botón es una edición completa, que se envía con el `base_seq` del estado que se ve y no se
 * da por guardada hasta el 201. Lo que pasa se anuncia en una región `aria-live`.
 */
export function EditBar({
  editor,
  editable,
  undoable,
  target,
  score,
  seq,
  multiStaff,
  keysId,
  focusScore,
  focusMemoryRef,
  suggestions,
  tab,
  onTab,
  keysShown,
  onToggleKeys,
  selection,
  onCommand,
  writing = null,
  onToggleWriting,
}: EditBarProps) {
  const suggestionsId = useId();
  const groupId = useId();
  const [ownTab, setOwnTab] = useState<ToolTab>("note");
  const activeTab = tab ?? ownTab;
  const chooseTab = onTab ?? setOwnTab;
  const tabRefs = useRef<Partial<Record<ToolTab, HTMLButtonElement | null>>>({});
  const showKeys = onToggleKeys ? (keysShown ?? false) : true;
  const { status, refusal, blocked, retry, targetRef } = editor;
  // La orden en espera se planea con la nota que la vista ofrece corregir en el estado que se ve.
  useLayoutEffect(() => {
    targetRef.current = { seq, target };
  });
  const said = feedback(status, multiStaff, score, retry);
  // Una orden que espera a que se guarde la que está en curso (ADR-0038) se dice en la barra.
  const text =
    editor.queued && status.kind === "saving"
      ? `${said.text} La orden siguiente espera su turno.`
      : said.text;
  const { reload } = said;
  const busy = status.kind === "saving" || status.kind === "reloading";

  // La figura que se dibuja: en un acorde, la de su primera nota, que cambia con todas (ADR-0049).
  const current = target ? figureOf(drawnDuration(target, score)) : { figure: null, dotted: false };
  const accidental = target?.event.kind === "note" ? accidentalOf(target.event.pitch) : null;
  // Las marcas de nota del evento elegido: en un acorde, las de su primera nota (ADR-0031).
  const holder = target && score ? marksHolder(score, target.anchor) : null;
  const marks = holder ? noteMarksOf(holder.event) : null;
  // La ligadura de prolongación de la nota elegida: si sale de ella y si le llega (ADR-0055).
  const tie = target?.event.kind === "note" ? (target.event.tie ?? null) : null;
  // Un hueco de la voz: sus botones escriben en él (ADR-0058).
  const gap = target !== null && isGap(target.event);
  const shared = {
    target,
    score,
    blocked,
    onRun: (command: PlannedCommand) => {
      if (onCommand) onCommand(command, target);
      else editor.run(command, target);
    },
  };
  // Hasta dónde llegan la clave y la armadura que se pongan en el compás elegido.
  const range = (attribute: "clef" | "key_signature") => {
    const found = target && score ? attributeRange(score, target.anchor, attribute) : null;
    return found ? ` · ${rangeName(found)}` : "";
  };
  // Y el compás, en toda la parte hasta el siguiente cambio (ADR-0044).
  const meterRange = target && score ? timeRange(score, target.anchor) : null;
  // Si desaparece el control que tenía el foco («Volver a aplicar» al enviarse, los botones al
  // finalizarse la sesión), el foco no se queda en el documento: pasa a la partitura o, si no lo
  // puede tomar, a lo que dice la barra.
  const lastFocused = useRef<HTMLElement | null>(null);
  const statusRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const last = lastFocused.current;
    if (!last || last.isConnected) return;
    lastFocused.current = null;
    const active = document.activeElement;
    if (active && active !== document.body) return;
    if (!focusScore?.()) statusRef.current?.focus({ preventScroll: true });
  });
  // La barra se monta en otro sitio cuando la partitura pasa a dibujarse (al deshacer la edición
  // que no se podía dibujar) o deja de poder dibujarse: el foco que tenía la anterior pasa al
  // mismo control de esta o, si no lo tiene, a lo que dice la barra; no se queda en el documento.
  const sectionRef = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    if (!focusMemoryRef) return;
    const section = sectionRef.current;
    const key = focusMemoryRef.current;
    focusMemoryRef.current = null;
    const active = document.activeElement;
    if (key !== null && (!active || active === document.body)) {
      const same = [...(section?.querySelectorAll("button") ?? [])].find(
        (button) => focusKey(button) === key,
      );
      (same ?? statusRef.current)?.focus({ preventScroll: true });
    }
    // Al desmontarse, la barra sigue en el documento: se apunta qué tenía el foco.
    return () => {
      const focused = document.activeElement;
      if (focused instanceof HTMLElement && section?.contains(focused)) {
        focusMemoryRef.current = focusKey(focused);
      }
    };
  }, [focusMemoryRef]);

  // La selección (#363): sus pasos en la primera fila y la nota elegida en la barra de estado.
  const steps = selection && selectionReady(selection.status) ? selection : null;
  // Las leyendas se ven tras «Atajos»; sin él (la sesión ya no se puede corregir), a la vista.
  const keysToggle = editable && onToggleKeys !== undefined;
  const legendShown = keysToggle ? showKeys : true;
  const hintText = editable && !writing ? hint(target) : null;
  // Escribiendo, la barra de estado dice cómo se escribe en lugar de la nota elegida: así no
  // crece a dos líneas al entrar en el modo y la partitura no se mueve.
  const readout = selection !== undefined && !(editable && writing !== null);

  return (
    <section
      ref={sectionRef}
      className="editor"
      aria-label="Corregir la nota elegida"
      data-busy={busy}
      onFocus={(event) => {
        lastFocused.current = event.target;
      }}
    >
      {/* Fila 1 (#363): deshacer y rehacer, las pestañas y «Escribir»; a la derecha, los pasos de
          la nota elegida y «Atajos». */}
      {(editable || undoable || steps !== null) && (
        <div className="editor__bar">
          <div className="editor__bar-start">
            {undoable && <HistoryControls editor={editor} multiStaff={multiStaff} score={score} />}
            {editable && (
              <div
                className="editor__tabs"
                role="tablist"
                aria-label="Herramientas de corrección"
                onKeyDown={(event) => {
                  const at = TOOL_TABS.findIndex(({ id }) => id === activeTab);
                  const next =
                    event.key === "ArrowRight"
                      ? (at + 1) % TOOL_TABS.length
                      : event.key === "ArrowLeft"
                        ? (at - 1 + TOOL_TABS.length) % TOOL_TABS.length
                        : event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? TOOL_TABS.length - 1
                            : null;
                  if (next === null) return;
                  event.preventDefault();
                  const chosen = TOOL_TABS[next];
                  if (!chosen) return;
                  chooseTab(chosen.id);
                  tabRefs.current[chosen.id]?.focus();
                }}
              >
                {TOOL_TABS.map(({ id, label }) => (
                  <button
                    key={id}
                    ref={(element) => {
                      tabRefs.current[id] = element;
                    }}
                    type="button"
                    role="tab"
                    id={`${groupId}-tab-${id}`}
                    className="editor__tab"
                    aria-selected={activeTab === id}
                    aria-controls={`${groupId}-panel-${id}`}
                    tabIndex={activeTab === id ? 0 : -1}
                    onClick={() => {
                      chooseTab(id);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            {editable && onToggleWriting && (
              <button
                type="button"
                className="editor__write"
                aria-pressed={writing !== null}
                aria-keyshortcuts="W"
                title="Escribir con el ratón (W)"
                onClick={onToggleWriting}
              >
                Escribir
              </button>
            )}
          </div>
          {(steps !== null || keysToggle) && (
            <div className="editor__bar-end">
              {steps && <SelectionSteps {...steps} />}
              {keysToggle && (
                <button
                  type="button"
                  className="editor__keys-toggle"
                  aria-expanded={showKeys}
                  aria-controls={[keysId, steps?.keysId].filter(Boolean).join(" ")}
                  onClick={onToggleKeys}
                >
                  Atajos
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {/* Fila 2 (#363): la paleta de la pestaña, en una fila. Las tres pestañas siguen montadas
          (ocultas las que no se ven): lo propuesto en un desplegable sin aplicar no se pierde al
          cambiar de pestaña (#341). */}
      {editable && (
        <div className="editor__palette">
          <div
            className="editor__groups"
            role="tabpanel"
            id={`${groupId}-panel-note`}
            aria-labelledby={`${groupId}-tab-note`}
            hidden={activeTab !== "note"}
          >
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-pitch`}>
              <p className="label editor__label" id={`${groupId}-pitch`}>
                Altura
              </p>
              <div className="editor__buttons">
                {PITCH.map((button) => (
                  <CommandButton key={button.label} {...button} {...shared} />
                ))}
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-accidental`}>
              <p className="label editor__label" id={`${groupId}-accidental`}>
                Alteración
              </p>
              <div className="editor__buttons">
                {ACCIDENTAL_BUTTONS.map((button) => (
                  <CommandButton
                    key={button.label}
                    command={{ kind: "accidental", accidental: button.accidental }}
                    label={button.label}
                    icon={button.icon}
                    pressed={accidental === button.accidental}
                    {...shared}
                  />
                ))}
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-figure`}>
              <p className="label editor__label" id={`${groupId}-figure`}>
                Figura
              </p>
              <div className="editor__buttons">
                {FIGURES.map((figure, index) => (
                  <CommandButton
                    key={figure.name}
                    command={{ kind: "figure", figure: index }}
                    label={figure.name}
                    icon={FIGURE_ICONS[index] ?? "figure-quarter"}
                    pressed={writing ? writing.figure === index : current.figure === index}
                    free={writing !== null}
                    {...shared}
                  />
                ))}
                <CommandButton
                  command={{ kind: "dot" }}
                  label="Puntillo"
                  icon="figure-dot"
                  pressed={writing ? writing.dotted : current.dotted}
                  free={writing !== null}
                  {...shared}
                />
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-structure`}>
              <p className="label editor__label" id={`${groupId}-structure`}>
                {gap ? "Hueco" : "Insertar antes o borrar"}
              </p>
              <div className="editor__buttons">
                {/* Los mismos tres botones en un hueco: la misma clave, para que el foco siga
                      en el que se pulsó cuando el hueco pasa a ser una nota (ADR-0058). */}
                {(gap ? GAP_STRUCTURE : STRUCTURE).map((button, index) => (
                  <CommandButton key={index} {...button} {...shared} />
                ))}
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-chord`}>
              <p className="label editor__label" id={`${groupId}-chord`}>
                Acorde y prolongación
              </p>
              <div className="editor__buttons">
                <CommandButton
                  command={{ kind: "chord-add" }}
                  label="Añadir una nota al acorde"
                  icon="plus"
                  text="Acorde"
                  {...shared}
                />
                <CommandButton
                  command={{ kind: "tie" }}
                  label="Ligar con la siguiente"
                  icon="mark-tie"
                  text="Ligar"
                  pressed={tieLeaves(tie)}
                  {...shared}
                />
              </div>
              {tieArrives(tie) && (
                <ul className="editor__spans" aria-labelledby={`${groupId}-chord`}>
                  <li>
                    <CommandButton
                      command={{ kind: "untie-in" }}
                      label="Quitar la ligadura que llega"
                      icon="cross"
                      text="Quitar la ligadura que llega"
                      {...shared}
                    />
                  </li>
                </ul>
              )}
            </div>
          </div>
          <div
            className="editor__groups"
            role="tabpanel"
            id={`${groupId}-panel-measure`}
            aria-labelledby={`${groupId}-tab-measure`}
            hidden={activeTab !== "measure"}
          >
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-tuplet`}>
              <p className="label editor__label" id={`${groupId}-tuplet`}>
                Tresillo
              </p>
              <div className="editor__buttons">
                {TUPLETS.map(({ scope, label, text }) => (
                  <CommandButton
                    key={scope}
                    command={{ kind: "tuplet", scope }}
                    label={label}
                    text={text}
                    pressed={tupletPressed(scope, target, score, editor.origin)}
                    origin={editor.origin}
                    {...shared}
                  />
                ))}
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-clef`}>
              <p className="label editor__label" id={`${groupId}-clef`}>
                {`Clave${range("clef")}`}
              </p>
              <div className="editor__buttons">
                {CLEFS.map((clef, index) => {
                  const command: PlannedCommand = { kind: "clef", clef: index };
                  const plan = planCommand(command, target, score);
                  return (
                    <CommandButton
                      key={clef.name}
                      command={command}
                      label={clef.name}
                      text={clef.word}
                      pressed={plan.kind === "refused" && plan.reason === "same"}
                      {...shared}
                    />
                  );
                })}
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-key`}>
              <p className="label editor__label" id={`${groupId}-key`}>
                {`Armadura${range("key_signature")}`}
              </p>
              <KeyPicker labelId={`${groupId}-key`} {...shared} />
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-time`}>
              <p className="label editor__label" id={`${groupId}-time`}>
                {`Compás${meterRange ? ` · ${rangeName(meterRange)}` : ""}`}
              </p>
              <TimePicker labelId={`${groupId}-time`} {...shared} />
            </div>
          </div>
          <div
            className="editor__groups"
            role="tabpanel"
            id={`${groupId}-panel-marks`}
            aria-labelledby={`${groupId}-tab-marks`}
            hidden={activeTab !== "marks"}
          >
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-marks`}>
              <p className="label editor__label" id={`${groupId}-marks`}>
                Articulaciones y calderón
              </p>
              <div className="editor__buttons">
                {ARTICULATIONS.map((articulation) => (
                  <CommandButton
                    key={articulation.value}
                    command={{ kind: "articulation", articulation: articulation.value }}
                    label={articulation.name}
                    icon={ARTICULATION_ICONS[articulation.value] ?? "mark-staccato"}
                    pressed={marks?.articulations.includes(articulation.value) ?? false}
                    {...shared}
                  />
                ))}
                <CommandButton
                  command={{ kind: "fermata" }}
                  label="Calderón"
                  icon="mark-fermata"
                  pressed={marks?.fermata ?? false}
                  {...shared}
                />
              </div>
            </div>
            <div className="editor__group" role="group" aria-labelledby={`${groupId}-dynamic`}>
              <p className="label editor__label" id={`${groupId}-dynamic`}>
                Dinámica
              </p>
              <DynamicPicker labelId={`${groupId}-dynamic`} {...shared} />
            </div>
            <div
              className="editor__group editor__group--spans"
              role="group"
              aria-labelledby={`${groupId}-spans`}
            >
              <p className="label editor__label" id={`${groupId}-spans`}>
                Ligadura y regulador
              </p>
              <SpanControls labelId={`${groupId}-spans`} editor={editor} {...shared} />
            </div>
          </div>
        </div>
      )}
      {editable && suggestions && suggestions.items.length > 0 && (
        <div
          className="editor__group editor__group--suggestions"
          role="group"
          aria-labelledby={suggestionsId}
        >
          <p className="label editor__label" id={suggestionsId}>
            Sugerencias para esta nota
          </p>
          <SuggestionList
            items={suggestions.items}
            labelOf={suggestions.labelOf}
            actions={suggestions.actions}
          />
        </div>
      )}
      {/* Barra de estado (#363): a la izquierda, la nota elegida o la indicación; a la derecha, lo
          que pasó con la última orden. */}
      <div className="editor__statusbar">
        {(readout || hintText !== null || (editable && writing !== null)) && (
          <div className="editor__now">
            {readout && (
              <SelectionReadout status={selection.status} description={selection.description} />
            )}
            {editable && writing ? (
              <p className="editor__hint editor__hint--writing">
                <span className="editor__hint-pointer">
                  Escribir: elige la figura y pasa el ratón por la partitura; clic para ponerla,
                  Mayús + clic para el acorde y Esc para salir.
                </span>
                <span className="editor__hint-touch">
                  Escribir: elige la figura y toca la partitura; vuelve a tocar en el mismo sitio
                  para ponerla y pulsa «Escribir» para salir.
                </span>
              </p>
            ) : (
              hintText !== null && <p className="editor__hint">{hintText}</p>
            )}
          </div>
        )}
        <div className="editor__feedback">
          <div className="editor__messages" role="status" ref={statusRef} tabIndex={-1}>
            <p className="editor__status">{text}</p>
            {/* Un rechazo no borra un aviso que hay que conservar, como el de un 409. */}
            {refusal && (
              <p className="editor__refusal">{distinct(refusal.message, refusal.nonce)}</p>
            )}
          </div>
          {retry?.plan.kind === "edit" && (
            <button
              type="button"
              className="link-button"
              aria-disabled={blocked}
              onClick={editor.reapply}
            >
              Volver a aplicar
            </button>
          )}
          {reload && (
            <button
              type="button"
              className="link-button"
              aria-disabled={busy || editor.held}
              onClick={() => {
                // Mientras se revalida, la recarga la hace la revalidación si hace falta (ADR-0035).
                if (!busy && !editor.held) void editor.reload();
              }}
            >
              Recargar la sesión
            </button>
          )}
        </div>
      </div>
      {/* Las leyendas de teclas: tras «Atajos», en un panel sobre la partitura que no la empuja. */}
      {(editable || steps !== null) && (
        <div className="editor__legend" data-popover={keysToggle} hidden={!legendShown}>
          {steps && <SelectionKeys keysId={steps.keysId} hidden={!legendShown} />}
          {editable && (
            <p className="editor__keys" id={keysId} hidden={!legendShown}>
              <span>
                <KeyCap>Mayús</KeyCap>
                <KeyCap icon="arrow-up">flecha arriba</KeyCap>
                <KeyCap icon="arrow-down">flecha abajo</KeyCap> paso
              </span>
              <span>
                <KeyCap>Mayús</KeyCap>
                <KeyCap>Re Pág</KeyCap>
                <KeyCap>Av Pág</KeyCap> octava
              </span>
              <span>
                <KeyCap>+</KeyCap>
                <KeyCap>−</KeyCap>
                <KeyCap>=</KeyCap> sostenido, bemol, becuadro
              </span>
              <span>
                <KeyCap>1</KeyCap> a <KeyCap>7</KeyCap> figura, de semifusa a redonda
              </span>
              <span>
                <KeyCap>.</KeyCap> puntillo
              </span>
              <span>
                <KeyCap>R</KeyCap> tresillo de tres figuras; <KeyCap>Mayús</KeyCap>
                <KeyCap>R</KeyCap> en todo el compás
              </span>
              <span>
                <KeyCap>N</KeyCap> nota antes (en un hueco, en él)
              </span>
              <span>
                <KeyCap>S</KeyCap> silencio antes (en un hueco, en él)
              </span>
              <span>
                <KeyCap>Supr</KeyCap> o <KeyCap>Retroceso</KeyCap> borrar
              </span>
              <span>
                <KeyCap>E</KeyCap> nota en el acorde
              </span>
              <span>
                <KeyCap>U</KeyCap> ligar con la siguiente
              </span>
              <span>
                <KeyCap>W</KeyCap> escribir con el ratón; <KeyCap>Esc</KeyCap> salir
              </span>
              <span>
                <KeyCap>P</KeyCap>
                <KeyCap>A</KeyCap>
                <KeyCap>M</KeyCap>
                <KeyCap>T</KeyCap> picado, acento, marcato, tenuto
              </span>
              <span>
                <KeyCap>C</KeyCap> calderón
              </span>
              <span>
                <KeyCap>I</KeyCap> inicio; <KeyCap>L</KeyCap>
                <KeyCap>&lt;</KeyCap>
                <KeyCap>&gt;</KeyCap> ligadura, crescendo, diminuendo hasta aquí
              </span>
              <span>
                <KeyCap>Ctrl</KeyCap> o <KeyCap>Cmd</KeyCap>
                <KeyCap>Z</KeyCap> deshacer
              </span>
              <span>
                <KeyCap>Ctrl</KeyCap> o <KeyCap>Cmd</KeyCap>
                <KeyCap>Mayús</KeyCap>
                <KeyCap>Z</KeyCap>, o <KeyCap>Ctrl</KeyCap>
                <KeyCap>Y</KeyCap> rehacer
              </span>
            </p>
          )}
        </div>
      )}
      {steps && <SelectionAnnouncement announcement={steps.announcement} />}
    </section>
  );
}
