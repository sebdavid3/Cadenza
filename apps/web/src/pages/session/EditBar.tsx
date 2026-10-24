import { useId } from "react";
import { PixelIcon, type PixelIconName } from "../../components/PixelIcon";
import type { AnchorPayload } from "../../types";
import {
  accidentalOf,
  figureOf,
  FIGURES,
  planEdit,
  type Accidental,
  type EditCommand,
  type EditTarget,
} from "./edits";
import type { Editor, EditorStatus, EditRequest } from "./editor";
import { KeyCap } from "./SelectionBar";

interface EditBarProps {
  editor: Editor;
  /** Si se ofrecen los controles: la sesión es de quien la ve y no está finalizada. */
  editable: boolean;
  /** Evento elegido en el estado que se muestra, o null si no hay ninguno que corregir. */
  target: EditTarget | null;
  /** Armadura del compás del evento elegido, en quintas. */
  fifths: number;
  multiStaff: boolean;
  /** Identificador de la leyenda de teclas, que también describe la partitura. */
  keysId: string;
}

const PITCH: {
  command: EditCommand;
  label: string;
  word: string;
  icon: PixelIconName;
  keys: string;
}[] = [
  {
    command: { kind: "step", direction: -1 },
    label: "Bajar un paso",
    word: "Paso",
    icon: "arrow-down",
    keys: "Shift+ArrowDown",
  },
  {
    command: { kind: "step", direction: 1 },
    label: "Subir un paso",
    word: "Paso",
    icon: "arrow-up",
    keys: "Shift+ArrowUp",
  },
  {
    command: { kind: "octave", direction: -1 },
    label: "Bajar una octava",
    word: "Octava",
    icon: "octave-down",
    keys: "Shift+PageDown",
  },
  {
    command: { kind: "octave", direction: 1 },
    label: "Subir una octava",
    word: "Octava",
    icon: "octave-up",
    keys: "Shift+PageUp",
  },
];

const ACCIDENTAL_BUTTONS: {
  accidental: Accidental;
  label: string;
  icon: PixelIconName;
  keys?: string;
}[] = [
  { accidental: "bb", label: "Doble bemol", icon: "accidental-double-flat" },
  { accidental: "b", label: "Bemol", icon: "accidental-flat", keys: "-" },
  { accidental: "", label: "Becuadro", icon: "accidental-natural", keys: "=" },
  { accidental: "#", label: "Sostenido", icon: "accidental-sharp", keys: "+" },
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

/** Dónde está el evento de una edición, para decirlo: «compás 2, voz 1». */
function placeOf(anchor: AnchorPayload, multiStaff: boolean): string {
  const place = `compás ${String(anchor.measure)}, voz ${String(anchor.voice + 1)}`;
  return multiStaff ? `pentagrama ${String(anchor.staff + 1)}, ${place}` : place;
}

/** Lo que se dice tras una orden, y si hace falta recargar para seguir. */
function feedback(
  status: EditorStatus,
  multiStaff: boolean,
  retry: Editor["retry"],
): { text: string; reload: boolean } {
  const what = (request: EditRequest) =>
    `${request.change} (${placeOf(request.anchor, multiStaff)})`;
  const inline = (request: EditRequest) =>
    `${request.change}, ${placeOf(request.anchor, multiStaff)}`;
  switch (status.kind) {
    case "idle":
      return { text: "", reload: false };
    case "saving":
      return { text: "Guardando…", reload: false };
    case "saved":
      return { text: `Guardado: ${status.request.change}.`, reload: false };
    case "refused":
      return { text: status.message, reload: false };
    case "conflict": {
      const base = `No se guardó: ${what(status.request)}. La sesión cambió en otra pestaña o dispositivo antes de guardarlo; ya ves su estado actual.`;
      if (!retry || retry.plan.kind === "edit") return { text: base, reload: false };
      // Sin nada que volver a aplicar, se dice por qué.
      const reason = retry.anchor
        ? retry.plan.message
        : "La nota que elegiste ya no está en el mismo sitio: elígela de nuevo si sigue haciendo falta.";
      return { text: `${base} ${reason}`, reload: false };
    }
    case "closed":
      return {
        text: `No se guardó: ${what(status.request)}. La sesión está finalizada y ya no admite correcciones.`,
        reload: false,
      };
    case "outdated":
      return {
        text: `No se guardó: ${what(status.request)}. La sesión cambió antes de guardarlo y no se pudo cargar su estado actual: recárgala para seguir.`,
        reload: true,
      };
    case "rejected":
      return {
        text: `El servidor no aceptó el cambio (${inline(status.request)}): no se guardó nada.`,
        reload: false,
      };
    case "forbidden":
      return {
        text: "No se guardó: solo la persona que hizo la transcripción puede corregirla.",
        reload: false,
      };
    case "missing":
      return {
        text: "No se guardó: la sesión ya no existe o no tienes acceso a ella.",
        reload: false,
      };
    case "unknown":
      return {
        text: `No hubo respuesta del servidor: puede que el cambio (${inline(status.request)}) no se guardara. Recarga la sesión para comprobarlo.`,
        reload: true,
      };
    case "unsynced":
      return {
        text: `Se guardó el cambio (${inline(status.request)}), pero no se pudo cargar la partitura nueva. Recarga la sesión para seguir corrigiendo.`,
        reload: true,
      };
    case "reloading":
      return { text: "Recargando la sesión…", reload: false };
    case "reloaded":
      return { text: "Sesión recargada.", reload: false };
    case "reload-failed":
      return {
        text: "No se pudo recargar la sesión. Comprueba la conexión e inténtalo de nuevo.",
        reload: true,
      };
  }
}

/** Qué hint dar bajo los controles según lo elegido. */
function hint(target: EditTarget | null): string | null {
  if (!target) return "Elige una nota o un silencio para corregirlo.";
  if (target.event.kind !== "note") return "Un silencio solo admite cambiar su figura.";
  if (target.chord) {
    return "En un acorde se cambian la altura y la alteración de cada nota; la figura, todavía no.";
  }
  return null;
}

interface CommandButtonProps {
  command: EditCommand;
  label: string;
  icon: PixelIconName;
  /** Palabra visible junto al icono; en una barra estrecha queda solo el icono. */
  word?: string;
  /** Tecla equivalente sobre la partitura (`aria-keyshortcuts`). */
  keys?: string;
  /** Si es el valor que ya tiene el evento: un conmutador pulsado. */
  pressed?: boolean;
  target: EditTarget | null;
  fifths: number;
  blocked: boolean;
  onRun: (command: EditCommand) => void;
}

/** Botón de una orden: inactivo si ahora no se puede; pulsado si es el valor que ya tiene. */
function CommandButton({
  command,
  label,
  icon,
  word,
  keys,
  pressed,
  target,
  fifths,
  blocked,
  onRun,
}: CommandButtonProps) {
  const plan = planEdit(command, target, fifths);
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
      aria-keyshortcuts={keys}
      onClick={() => {
        if (!disabled) onRun(command);
      }}
    >
      <PixelIcon name={icon} />
      {word && <span className="editor__word">{word}</span>}
    </button>
  );
}

/**
 * Barra de corrección de la nota elegida (ADR-0030): altura, alteración y figura. Cada botón es
 * una edición completa, que se envía con el `base_seq` del estado que se ve y no se da por
 * guardada hasta el 201. Lo que pasa se anuncia en una región `aria-live`.
 */
export function EditBar({ editor, editable, target, fifths, multiStaff, keysId }: EditBarProps) {
  const groupId = useId();
  const { status, blocked, retry } = editor;
  const { text, reload } = feedback(status, multiStaff, retry);
  const busy = status.kind === "saving" || status.kind === "reloading";

  const current = target ? figureOf(target.event.duration_beats) : { figure: null, dotted: false };
  const accidental = target?.event.kind === "note" ? accidentalOf(target.event.pitch) : null;
  const shared = {
    target,
    fifths,
    blocked,
    onRun: (command: EditCommand) => {
      editor.run(command, target);
    },
  };

  return (
    <section className="editor" aria-label="Corregir la nota elegida" data-busy={busy}>
      {editable && (
        <>
          <div className="editor__groups">
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
                    keys={button.keys}
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
                    keys={figure.key}
                    pressed={current.figure === index}
                    {...shared}
                  />
                ))}
                <CommandButton
                  command={{ kind: "dot" }}
                  label="Puntillo"
                  icon="figure-dot"
                  keys="."
                  pressed={current.dotted}
                  {...shared}
                />
              </div>
            </div>
          </div>
          {hint(target) !== null && <p className="editor__hint">{hint(target)}</p>}
        </>
      )}
      <div className="editor__feedback">
        <p className="editor__status" role="status">
          {text}
        </p>
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
            aria-disabled={busy}
            onClick={() => {
              void editor.reload();
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
        </p>
      )}
    </section>
  );
}
