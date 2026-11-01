import { useState } from "react";
import type { ScoreIRPayload } from "../../types";
import { planCommand, type EditTarget, type PlannedCommand } from "./edits";
import { activeTime, timeKey, timeLabel, TIME_SIGNATURES, type TimeChoice } from "./meterEdits";

interface TimePickerProps {
  /** Rótulo del grupo, que nombra el desplegable. */
  labelId: string;
  target: EditTarget | null;
  score: ScoreIRPayload | null;
  blocked: boolean;
  onRun: (command: PlannedCommand) => void;
}

/** Lo que propone el desplegable sin compás en la partitura: 4/4 con números. */
const FALLBACK: TimeChoice = { beats: 4, beat_type: 4, symbol: null };

/**
 * Indicación de compás desde el compás elegido (#241, ADR-0048): un desplegable con C, ¢ y las
 * más usadas con números, y «Cambiar», que la envía. Como el de la armadura (ADR-0033), el
 * desplegable solo propone: con el teclado cada flecha cambia su valor y cada valor no es una
 * edición. Propone la que rige el compás elegido y vuelve a ella al cambiar de compás o de
 * indicación, sin montarse de nuevo: el foco se queda en «Cambiar» tras guardar.
 */
export function TimePicker({ labelId, target, score, blocked, onRun }: TimePickerProps) {
  const current = (target && score ? activeTime(score, target.anchor) : null) ?? FALLBACK;
  // Una indicación que no está en la lista (7/4, 5/16…) también se ofrece: es la que rige.
  const choices = TIME_SIGNATURES.some((choice) => timeKey(choice) === timeKey(current))
    ? TIME_SIGNATURES
    : [current, ...TIME_SIGNATURES];
  const origin = target
    ? `${String(target.anchor.part)}:${String(target.anchor.measure)}:${timeKey(current)}`
    : null;
  const [draft, setDraft] = useState<{ origin: string | null; key: string }>({
    origin,
    key: timeKey(current),
  });
  // Lo propuesto vale para un compás y su indicación: al pasar a otro (o al guardarla) se olvida.
  if (draft.origin !== origin) setDraft({ origin, key: timeKey(current) });
  const key = draft.origin === origin ? draft.key : timeKey(current);
  const chosen = choices.find((choice) => timeKey(choice) === key) ?? current;
  const command: PlannedCommand = { kind: "time", time: chosen };
  const plan = planCommand(command, target, score);
  // Si los pentagramas de la parte no llevan el mismo compás, pulsar «Cambiar» lo dice.
  const disabled = blocked || (plan.kind === "refused" && plan.reason !== "meter");
  return (
    <div className="editor__buttons">
      <select
        className="editor__select"
        aria-labelledby={labelId}
        value={key}
        disabled={!target}
        onChange={(event) => {
          setDraft({ origin, key: event.target.value });
        }}
      >
        {choices.map((choice) => (
          <option key={timeKey(choice)} value={timeKey(choice)}>
            {timeLabel(choice)}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="editor__button"
        aria-label="Cambiar compás"
        title="Cambiar compás"
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
