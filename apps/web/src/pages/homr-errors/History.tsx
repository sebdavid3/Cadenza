import { useEffect, useState } from "react";
import { ApiError } from "../../api/errors";
import type { HomrErrorHistoryRowRead, HomrErrorScoreRead } from "../../types";
import { ExamplesPanel, Pager } from "./Examples";
import {
  type ExamplesContent,
  scoreImageUrl,
  type ScoreLoader,
  scoreSelection,
  type Selection,
} from "./selection";
import {
  fmt,
  HISTORY_SIZES,
  HISTORY_SORTS,
  historyRows,
  type HistorySort,
  pct,
  plural,
} from "./stats";

// El historial de transcripciones de un corpus público (#424, ADR-0073), como el del informe
// local (#418): todas sus partituras, con buscador, orden y páginas. Elegir una pide su detalle
// (`GET /stats/homr-errors/{grupo}/scores/{id}`) y enseña sus correcciones en el panel de los
// ejemplos. Los grupos de Cadenza no tienen historial: nada de una transcripción concreta.

const CLEAN = "HOMR la leyó sin ninguna corrección.";

const EMPTY = { examples: [], bars: {}, figures: {} };

/** Las correcciones de una partitura del historial. Sin ninguna, no hace falta pedirlas. */
export function ScoreExamples(props: {
  group: string;
  row: HomrErrorHistoryRowRead;
  selected: Selection;
  corpus: string;
  load: ScoreLoader;
}) {
  if (!props.row.fixes) {
    return (
      <ExamplesPanel
        content={{ ...EMPTY, empty: CLEAN }}
        selected={props.selected}
        corpus={props.corpus}
      />
    );
  }
  return <FetchedScoreExamples {...props} />;
}

type Detail =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "gone" }
  | { status: "ready"; detail: HomrErrorScoreRead };

/** Se monta de nuevo con cada partitura elegida (`key` en quien lo usa): la pide una vez. */
function FetchedScoreExamples({
  group,
  row,
  selected,
  corpus,
  load,
}: {
  group: string;
  row: HomrErrorHistoryRowRead;
  selected: Selection;
  corpus: string;
  load: ScoreLoader;
}) {
  const [attempt, setAttempt] = useState(0);
  const [detail, setDetail] = useState<Detail>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    load(group, row.id, controller.signal).then(
      (found) => {
        if (!controller.signal.aborted) setDetail({ status: "ready", detail: found });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        // Un 404: el corpus cambió desde que se cargó la página y la partitura ya no está.
        setDetail({
          status: error instanceof ApiError && error.status === 404 ? "gone" : "failed",
        });
      },
    );
    return () => {
      controller.abort();
    };
  }, [group, row.id, load, attempt]);

  let content: ExamplesContent;
  if (detail.status === "ready") {
    const { examples, bars, figures, image } = detail.detail;
    // Todos sus ejemplos son de la misma partitura: la misma imagen.
    const url = image ? scoreImageUrl(group, row.id) : null;
    content = { examples, bars, figures, empty: CLEAN, imageOf: () => url };
  } else if (detail.status === "loading") {
    content = { ...EMPTY, empty: "Cargando sus correcciones…" };
  } else if (detail.status === "gone") {
    content = {
      ...EMPTY,
      empty: "Esta partitura ya no está en el historial: el corpus cambió. Recarga la página.",
    };
  } else {
    content = {
      ...EMPTY,
      empty: "Ahora no se pueden cargar sus correcciones.",
      retry: () => {
        // El botón desaparece al reintentar: el foco pasa al título del panel.
        document.getElementById("homr-ex-title")?.focus();
        setDetail({ status: "loading" });
        setAttempt((n) => n + 1);
      },
    };
  }
  return <ExamplesPanel content={content} selected={selected} corpus={corpus} />;
}

export function HistoryPanel({
  history,
  selected,
  onChoose,
}: {
  history: HomrErrorHistoryRowRead[];
  selected: Selection | null;
  onChoose: (selection: Selection) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<HistorySort>("rate");
  const [size, setSize] = useState<number>(HISTORY_SIZES[0]);
  const [page, setPage] = useState(0);
  const rows = historyRows(history, query, sort);
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.min(page, pages - 1);
  const start = current * size;
  const shown = rows.slice(start, start + size);
  const total = plural(history.length, "transcripción", "transcripciones");
  const found = plural(rows.length, "transcripción", "transcripciones");
  const searching = query.trim() !== "";
  let count = searching ? `${found} de ${fmt(history.length)}` : total;
  if (pages > 1) {
    count = `${fmt(start + 1)}–${fmt(start + shown.length)} de ${searching ? `${found} (de ${fmt(history.length)})` : total}`;
  }

  return (
    <section className="homr__panel homr__history" aria-labelledby="homr-history">
      <h3 id="homr-history">Historial de transcripciones</h3>
      <p className="homr__panel-note">
        Todas las partituras del corpus. Busca una por su nombre y elígela para ver sus correcciones
        con el compás dibujado. Las correcciones cuentan también las notas que HOMR no leyó, la
        clave y la armadura.
      </p>
      <div className="homr__history-tools">
        <label className="homr__history-search">
          <span className="label homr__muted">Buscar</span>
          <input
            type="search"
            value={query}
            placeholder="000100134, 7_1_1…"
            autoComplete="off"
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
          />
        </label>
        <label>
          <span className="label homr__muted">Orden</span>
          <select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as HistorySort);
              setPage(0);
            }}
          >
            {HISTORY_SORTS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label homr__muted">Por página</span>
          <select
            value={size}
            onChange={(event) => {
              setSize(Number(event.target.value));
              setPage(0);
            }}
          >
            {HISTORY_SIZES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <p className="homr__history-count" aria-live="polite">
          {count}
        </p>
      </div>
      {shown.length ? (
        <div className="homr__scroll" role="region" aria-label="Tabla del historial" tabIndex={0}>
          <table className="homr__history-table">
            <thead>
              <tr>
                <th scope="col">Partitura</th>
                <th scope="col" className="homr__n">
                  Notas leídas
                </th>
                <th scope="col" className="homr__n">
                  Correcciones
                </th>
                <th scope="col" className="homr__n">
                  Por nota
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => {
                const selection = scoreSelection(row);
                const choose = () => {
                  onChoose(selection);
                };
                return (
                  // La fila entera se elige con el ratón; con el teclado, su botón (el clic de
                  // este sube hasta la fila).
                  <tr key={row.id} onClick={choose}>
                    <th scope="row">
                      <button
                        type="button"
                        className="homr__history-pick"
                        aria-current={selected?.key === selection.key ? "true" : undefined}
                      >
                        {row.label}
                      </button>
                    </th>
                    <td className="homr__n">{fmt(row.read)}</td>
                    <td className={row.fixes ? "homr__n" : "homr__n homr__clean"}>
                      {row.fixes ? fmt(row.fixes) : "ninguna"}
                    </td>
                    <td className="homr__n">{row.fixes ? pct(row.fixes, row.read, 0) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="homr__panel-note">Ninguna transcripción coincide con «{query.trim()}».</p>
      )}
      <Pager label="Páginas del historial" page={current} pages={pages} onPage={setPage} />
    </section>
  );
}
