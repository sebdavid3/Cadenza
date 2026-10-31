import { useId, useLayoutEffect, useRef, useState, type MutableRefObject } from "react";
import { PixelIcon, type PixelIconName } from "../../components/PixelIcon";
import type { ScoreIRPayload } from "../../types";
import {
  accidentalOf,
  activeFifths,
  attributeRange,
  CLEFS,
  figureOf,
  FIGURES,
  keyLabel,
  planCommand,
  rangeName,
  type Accidental,
  type EditCommand,
  type EditTarget,
} from "./edits";
import type { Editor, EditorRequest, EditorStatus } from "./editor";
import { describeEdit, hasCompleteBefore, placeOf } from "./history";
import { KeyCap } from "./SelectionBar";
import type { EditEventRead } from "../../types";

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
  /** Si se puede elegir una nota sobre la partitura; si no, lo dice la barra de la selección. */
  available: boolean;
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
}

const PITCH: { command: EditCommand; label: string; word: string; icon: PixelIconName }[] = [
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
  command: EditCommand;
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
      return { text: distinct(status.message, status.nonce), reload: false };
    case "conflict": {
      const { request } = status;
      const words = WORDS[request.kind];
      const base = `${words.notDone}: ${what(request)}. La sesión cambió en otra pestaña o dispositivo antes de ${words.it}; ya ves su estado actual.`;
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

/** Qué indicar bajo los controles según lo elegido. */
function hint(target: EditTarget | null, available: boolean): string | null {
  // Si no se puede elegir nota, ya lo dice la barra de la selección.
  if (!target) return available ? "Elige una nota o un silencio para corregirlo." : null;
  if (target.event.kind !== "note") return "Un silencio no tiene altura ni alteración.";
  if (target.chord) {
    return "En un acorde se cambian la altura y la alteración de cada nota, pero todavía no la figura; su primera nota se borra después de las demás.";
  }
  return null;
}

interface CommandButtonProps {
  command: EditCommand;
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
  blocked: boolean;
  onRun: (command: EditCommand) => void;
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
  blocked,
  onRun,
}: CommandButtonProps) {
  const plan = planCommand(command, target, score);
  // El valor que ya tiene no está inactivo: está pulsado, y pulsarlo lo dice.
  const disabled = blocked || (plan.kind === "refused" && plan.reason !== "same");
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
  onRun: (command: EditCommand) => void;
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
  const command: EditCommand = { kind: "key", fifths };
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
      <p className="editor__history" id={noteId}>
        {note}
      </p>
    </div>
  );
}

/**
 * Barra de corrección de la nota elegida (ADR-0030, ADR-0033): altura, alteración y figura;
 * insertar antes y borrar; la clave y la armadura de su compás; y deshacer y rehacer (ADR-0034).
 * Cada botón es una edición completa, que se envía con el `base_seq` del estado que se ve y no se
 * da por guardada hasta el 201. Lo que pasa se anuncia en una región `aria-live`.
 */
export function EditBar({
  editor,
  editable,
  undoable,
  target,
  available,
  score,
  seq,
  multiStaff,
  keysId,
  focusScore,
  focusMemoryRef,
}: EditBarProps) {
  const groupId = useId();
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

  const current = target ? figureOf(target.event.duration_beats) : { figure: null, dotted: false };
  const accidental = target?.event.kind === "note" ? accidentalOf(target.event.pitch) : null;
  const shared = {
    target,
    score,
    blocked,
    onRun: (command: EditCommand) => {
      editor.run(command, target);
    },
  };
  // Hasta dónde llegan la clave y la armadura que se pongan en el compás elegido.
  const range = (attribute: "clef" | "key_signature") => {
    const found = target && score ? attributeRange(score, target.anchor, attribute) : null;
    return found ? ` · ${rangeName(found)}` : "";
  };
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
      {(editable || undoable) && (
        <div className="editor__groups">
          {undoable && <HistoryControls editor={editor} multiStaff={multiStaff} score={score} />}
          {editable && (
            <>
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
                      pressed={current.figure === index}
                      {...shared}
                    />
                  ))}
                  <CommandButton
                    command={{ kind: "dot" }}
                    label="Puntillo"
                    icon="figure-dot"
                    pressed={current.dotted}
                    {...shared}
                  />
                </div>
              </div>
              <div className="editor__group" role="group" aria-labelledby={`${groupId}-structure`}>
                <p className="label editor__label" id={`${groupId}-structure`}>
                  Insertar antes o borrar
                </p>
                <div className="editor__buttons">
                  {STRUCTURE.map((button) => (
                    <CommandButton key={button.label} {...button} {...shared} />
                  ))}
                </div>
              </div>
              <div className="editor__group" role="group" aria-labelledby={`${groupId}-clef`}>
                <p className="label editor__label" id={`${groupId}-clef`}>
                  {`Clave${range("clef")}`}
                </p>
                <div className="editor__buttons">
                  {CLEFS.map((clef, index) => {
                    const command: EditCommand = { kind: "clef", clef: index };
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
            </>
          )}
        </div>
      )}
      {editable && hint(target, available) !== null && (
        <p className="editor__hint">{hint(target, available)}</p>
      )}
      <div className="editor__feedback">
        <div className="editor__messages" role="status" ref={statusRef} tabIndex={-1}>
          <p className="editor__status">{text}</p>
          {/* Un rechazo no borra un aviso que hay que conservar, como el de un 409. */}
          {refusal && <p className="editor__refusal">{distinct(refusal.message, refusal.nonce)}</p>}
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
      {editable && (
        <p className="editor__keys" id={keysId}>
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
            <KeyCap>N</KeyCap> nota antes
          </span>
          <span>
            <KeyCap>S</KeyCap> silencio antes
          </span>
          <span>
            <KeyCap>Supr</KeyCap> o <KeyCap>Retroceso</KeyCap> borrar
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
    </section>
  );
}
