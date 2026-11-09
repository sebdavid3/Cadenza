/** Qué se puede hacer con la selección de notas en la partitura dibujada. */
export type SelectionStatus =
  | { kind: "pending" }
  | { kind: "ready"; empty: boolean }
  /** No se ofrece: OSMD dibujó otros compases (sin recuento) o no todos los eventos cuadran. */
  | { kind: "unavailable"; total?: number; unmatched?: number };

/** Evento elegido: dónde está y qué es. */
export type SelectionDescription = { place: string; what: string } | null;

/**
 * Lo que la partitura ofrece de la selección: su estado, la nota elegida, el anuncio y los pasos.
 * Sin barra de corrección se muestra en su propia franja; con ella, sus pasos van en la primera
 * fila de la barra y la nota elegida en su barra de estado (#363).
 */
export interface SelectionControls {
  status: SelectionStatus;
  description: SelectionDescription;
  announcement: string;
  /** Identificador de la leyenda de teclas, que describe la partitura. */
  keysId: string;
  onPrevious: () => void;
  onNext: () => void;
  onClear: () => void;
}

/** Si se pueden elegir notas: entonces hay pasos, leyenda y nota elegida. */
export function selectionReady(status: SelectionStatus): boolean {
  return status.kind === "ready" && !status.empty;
}
