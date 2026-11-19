// Qué enseña el panel de los ejemplos de un corpus (#424): los de una cifra, que vienen con el
// grupo, o los de una partitura del historial, que se piden al elegirla.

import { resolveBaseUrl } from "../../api/config";
import { api } from "../../api/instance";
import type {
  DrawnBarRead,
  FigureRead,
  HomrErrorExampleRead,
  HomrErrorHistoryRowRead,
  HomrErrorScoreRead,
  HomrErrorStatsValuesRead,
} from "../../types";

export interface Selection {
  key: string;
  title: string;
  kicker: string;
}

/** Lo que enseña el panel: unos ejemplos con sus compases y sus figuras, o por qué no hay. */
export interface ExamplesContent {
  examples: HomrErrorExampleRead[];
  bars: Record<string, DrawnBarRead>;
  figures: Record<string, FigureRead>;
  /** Sin ejemplos, lo que se dice en su lugar. */
  empty: string;
  /** Si no se pudieron cargar, cómo volver a pedirlos. */
  retry?: () => void;
  /** La imagen del corpus de la partitura de un ejemplo, si la tiene. */
  imageOf?: (example: HomrErrorExampleRead) => string | null;
}

const scorePath = (group: string, score: string): `/${string}` =>
  `/stats/homr-errors/${encodeURIComponent(group)}/scores/${encodeURIComponent(score)}`;

/** Dónde está la imagen del corpus de una partitura (`image` en su fila del historial). */
export function scoreImageUrl(group: string, score: string): string {
  return `${resolveBaseUrl().replace(/\/+$/, "")}${scorePath(group, score)}/image`;
}

/** Los ejemplos de una cifra elegida, de los que publica el grupo, con la imagen de su
 * partitura si el historial dice que la tiene. */
export function figureExamples(
  group: string,
  stats: HomrErrorStatsValuesRead,
  selected: Selection | null,
): ExamplesContent {
  const ids = selected ? (stats.example_keys?.[selected.key] ?? []) : [];
  const withImage = new Map(
    (stats.history ?? []).filter((row) => row.image).map((row) => [row.label, row.id]),
  );
  return {
    imageOf: (example) => {
      const score = withImage.get(example.score);
      return score === undefined ? null : scoreImageUrl(group, score);
    },
    examples: ids.flatMap((i) => {
      const example = stats.examples?.[i];
      return example ? [example] : [];
    }),
    bars: stats.bars ?? {},
    figures: stats.figures,
    empty: selected
      ? "Ningún ejemplo de esta cifra."
      : "Elige una cifra, una barra, una columna, una casilla o una partitura del historial para ver sus ejemplos.",
  };
}

export type ScoreLoader = (
  group: string,
  score: string,
  signal: AbortSignal,
) => Promise<HomrErrorScoreRead>;

export const loadScore: ScoreLoader = (group, score, signal) =>
  api.request<HomrErrorScoreRead>(scorePath(group, score), { auth: false, signal });

/** La clave de una partitura elegida, como en el informe: `score:<íncipit>`. */
export const SCORE_PREFIX = "score:";

const KICKER = "Historial de transcripciones";

export function scoreSelection(row: HomrErrorHistoryRowRead): Selection {
  return { key: `${SCORE_PREFIX}${row.id}`, title: row.label, kicker: KICKER };
}
