import { useEffect, useRef, type FormEvent } from "react";
import "../../components/button.css";
import { formatSize } from "./format";
import { useQueueStore, type PreparedItem } from "./queue";
import { ScoreDataFields, type PartField } from "./ScoreDataFields";
import type { ScoreDataDraft } from "./scoreData";

/** Las dos partes que se piden al subir, de arriba abajo (ADR-0041 §3). */
const UPLOAD_PARTS: PartField[] = [
  { label: "Parte de arriba", hint: "La voz o el instrumento del pentagrama de arriba." },
  {
    label: "Segunda parte",
    hint: "El piano que acompaña, si lo hay. Si la partitura no la tiene, se ignora.",
  },
];

const copy = (draft: ScoreDataDraft): ScoreDataDraft => ({
  ...draft,
  parts: draft.parts.map((part) => ({ ...part })),
});

interface PreparePanelProps {
  /**
   * Si el foco va al nombre al aparecer: sí cuando se acaban de elegir las imágenes, no cuando
   * la vista vuelve a montarse con imágenes que ya esperaban.
   */
  focusOnOpen: boolean;
  /** Tras enviar el lote: el foco pasa a la cola. */
  onSent: () => void;
  /** Tras descartarlo o quitar la última imagen: el foco vuelve a «Elegir imágenes». */
  onClosed: () => void;
}

/**
 * Antes de transcribir (#240, ADR-0045): las imágenes elegidas esperan aquí con los datos de la
 * partitura. Valen para todas o se cambian en cada una; todo es opcional y, sin nombre, la sesión
 * se llama como su archivo. Nada se envía hasta pulsar «Transcribir».
 */
export function PreparePanel({ focusOnOpen, onSent, onClosed }: PreparePanelProps) {
  const prepared = useQueueStore((state) => state.prepared);
  const common = useQueueStore((state) => state.common);
  const setCommon = useQueueStore((state) => state.setCommon);
  const setOwn = useQueueStore((state) => state.setOwn);
  const unprepare = useQueueStore((state) => state.unprepare);
  const discard = useQueueStore((state) => state.discardPrepared);
  const submit = useQueueStore((state) => state.submitPrepared);
  const batch = prepared.length > 1;

  // Al aparecer, el foco va al primer dato: elegir las imágenes es empezar a describirlas.
  const titleRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const focusRequested = useRef(focusOnOpen);
  useEffect(() => {
    if (focusRequested.current) titleRef.current?.focus();
  }, []);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
    onSent();
  }

  function remove(item: PreparedItem) {
    if (prepared.length === 1) {
      unprepare(item.id);
      onClosed();
      return;
    }
    unprepare(item.id);
    headingRef.current?.focus();
  }

  return (
    <form className="prepare" aria-labelledby="prepare-title" onSubmit={onSubmit} noValidate>
      <div className="prepare__head">
        <h2 id="prepare-title" className="panel__title" ref={headingRef} tabIndex={-1}>
          Antes de transcribir
        </h2>
        <p className="label prepare__count" aria-live="polite">
          {batch ? `${String(prepared.length)} imágenes` : "1 imagen"}
        </p>
      </div>
      <p className="prepare__lead">
        Todo es opcional y se puede cambiar después desde la sesión. Los instrumentos se asignan por
        orden, de arriba abajo, y son los que sonarán al reproducirla.
      </p>
      <fieldset className="prepare__common">
        <legend className="prepare__legend">
          {batch ? "Datos para todas las imágenes" : "Datos de la partitura"}
        </legend>
        <ScoreDataFields
          value={common}
          onChange={setCommon}
          parts={UPLOAD_PARTS}
          titleRef={titleRef}
          titleHint={
            batch
              ? "Sin nombre, cada sesión se llama como su archivo."
              : "Sin nombre, la sesión se llama como el archivo."
          }
        />
      </fieldset>
      {/* role="list": sin viñetas, Safari y VoiceOver dejan de tratarla como lista. */}
      <ul className="prepare__list" role="list" aria-label="Imágenes elegidas">
        {prepared.map((item) => (
          <PreparedRow
            key={item.id}
            item={item}
            batch={batch}
            common={common}
            onOwn={(own) => {
              setOwn(item.id, own);
            }}
            onRemove={() => {
              remove(item);
            }}
          />
        ))}
      </ul>
      <div className="prepare__actions">
        <button type="submit" className="button button--primary">
          {batch ? `Transcribir ${String(prepared.length)} imágenes` : "Transcribir la imagen"}
        </button>
        <button
          type="button"
          className="link-button"
          onClick={() => {
            discard();
            onClosed();
          }}
        >
          Descartar
        </button>
      </div>
    </form>
  );
}

interface PreparedRowProps {
  item: PreparedItem;
  batch: boolean;
  common: ScoreDataDraft;
  onOwn: (own: ScoreDataDraft | null) => void;
  onRemove: () => void;
}

function PreparedRow({ item, batch, common, onOwn, onRemove }: PreparedRowProps) {
  const ownId = `prepare-own-${item.id}`;
  const ownTitleRef = useRef<HTMLInputElement>(null);
  const focusOwn = useRef(false);
  useEffect(() => {
    if (!focusOwn.current || !item.own) return;
    focusOwn.current = false;
    ownTitleRef.current?.focus();
  });
  const name = (item.own ?? common).title.trim() || item.file.name;

  return (
    <li className="prepare__item">
      <div className="prepare__file">
        <span className="prepare__name">{item.file.name}</span>
        <span className="label prepare__meta">{formatSize(item.file.size)}</span>
        {batch && <span className="prepare__will">Se llamará «{name}»</span>}
      </div>
      <div className="prepare__item-actions">
        {batch && (
          <button
            type="button"
            className="link-button"
            aria-controls={item.own ? ownId : undefined}
            aria-label={
              item.own
                ? `Usar los datos comunes en ${item.file.name}`
                : `Cambiar los datos de ${item.file.name}`
            }
            onClick={() => {
              if (item.own) {
                onOwn(null);
              } else {
                focusOwn.current = true;
                onOwn(copy(common));
              }
            }}
          >
            {item.own ? "Usar los datos comunes" : "Cambiar los datos"}
          </button>
        )}
        <button
          type="button"
          className="link-button"
          aria-label={`Quitar ${item.file.name}`}
          onClick={onRemove}
        >
          Quitar
        </button>
      </div>
      {batch && item.own && (
        <fieldset id={ownId} className="prepare__own">
          <legend className="prepare__legend">Datos de {item.file.name}</legend>
          <ScoreDataFields
            value={item.own}
            onChange={onOwn}
            parts={UPLOAD_PARTS}
            titleRef={ownTitleRef}
            titleHint="Sin nombre, la sesión se llama como el archivo."
          />
        </fieldset>
      )}
    </li>
  );
}
