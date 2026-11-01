import { useId, type Ref } from "react";
import type { Instrument } from "../../types";
import {
  COMPOSER_MAX_LENGTH,
  INSTRUMENT_OPTIONS,
  PART_NAME_MAX_LENGTH,
  TITLE_MAX_LENGTH,
  withInstrument,
  type ScoreDataDraft,
} from "./scoreData";
import "./score-data.css";

export interface PartField {
  label: string;
  hint?: string;
}

interface ScoreDataFieldsProps {
  value: ScoreDataDraft;
  onChange: (value: ScoreDataDraft) => void;
  /** Rótulo de cada parte, en el orden de `value.parts`. */
  parts: PartField[];
  /** Qué pasa si no se da nombre. */
  titleHint: string;
  titleRef?: Ref<HTMLInputElement>;
  /** Mientras se guarda, los campos se leen pero no se cambian. */
  readOnly?: boolean;
}

/**
 * Los datos de una partitura (#240, ADR-0045): su nombre, su compositor y el instrumento de cada
 * parte, de la lista cerrada de #235. «Otro» pide el nombre del instrumento y suena como el piano.
 * Todo es opcional. Lo usan el formulario de antes de transcribir y el de la vista de la sesión.
 */
export function ScoreDataFields({
  value,
  onChange,
  parts,
  titleHint,
  titleRef,
  readOnly = false,
}: ScoreDataFieldsProps) {
  const id = useId();
  const setPart = (index: number, change: (part: ScoreDataDraft["parts"][number]) => void) => {
    onChange({
      ...value,
      parts: value.parts.map((part, at) => {
        if (at !== index) return part;
        const next = { ...part };
        change(next);
        return next;
      }),
    });
  };

  return (
    <div className="score-data">
      <div className="score-data__field score-data__field--wide">
        <label className="label" htmlFor={`${id}-title`}>
          Nombre de la partitura
        </label>
        <input
          ref={titleRef}
          id={`${id}-title`}
          className="score-data__input"
          value={value.title}
          maxLength={TITLE_MAX_LENGTH}
          autoComplete="off"
          readOnly={readOnly}
          aria-describedby={`${id}-title-hint`}
          onChange={(event) => {
            onChange({ ...value, title: event.target.value });
          }}
        />
        <p id={`${id}-title-hint`} className="score-data__hint">
          {titleHint}
        </p>
      </div>
      <div className="score-data__field score-data__field--wide">
        <label className="label" htmlFor={`${id}-composer`}>
          Compositor
        </label>
        <input
          id={`${id}-composer`}
          className="score-data__input"
          value={value.composer}
          maxLength={COMPOSER_MAX_LENGTH}
          autoComplete="off"
          readOnly={readOnly}
          onChange={(event) => {
            onChange({ ...value, composer: event.target.value });
          }}
        />
      </div>
      {value.parts.map((part, index) => {
        const field = parts[index];
        const partId = `${id}-part-${String(index)}`;
        return (
          <div className="score-data__field" key={partId}>
            <label className="label" htmlFor={partId}>
              {field?.label ?? `Parte ${String(index + 1)}`}
            </label>
            <select
              id={partId}
              className="score-data__input score-data__select"
              value={part.instrument}
              disabled={readOnly}
              aria-describedby={field?.hint ? `${partId}-hint` : undefined}
              onChange={(event) => {
                const instrument = event.target.value as Instrument | "";
                onChange({
                  ...value,
                  parts: value.parts.map((current, at) =>
                    at === index ? withInstrument(current, instrument) : current,
                  ),
                });
              }}
            >
              {INSTRUMENT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {field?.hint && (
              <p id={`${partId}-hint`} className="score-data__hint">
                {field.hint}
              </p>
            )}
            {part.instrument === "other" && (
              <div className="score-data__other">
                <label className="label" htmlFor={`${partId}-name`}>
                  Nombre del instrumento
                </label>
                <input
                  id={`${partId}-name`}
                  className="score-data__input"
                  value={part.name}
                  maxLength={PART_NAME_MAX_LENGTH}
                  autoComplete="off"
                  readOnly={readOnly}
                  aria-describedby={`${partId}-name-hint`}
                  onChange={(event) => {
                    const name = event.target.value;
                    setPart(index, (next) => {
                      next.name = name;
                    });
                  }}
                />
                <p id={`${partId}-name-hint`} className="score-data__hint">
                  Suena como el piano.
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
