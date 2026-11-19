import { useState, type ReactNode } from "react";
import type { FigureRead, HomrErrorExampleRead, HomrErrorStatsValuesRead } from "../../types";
import { DrawnBar } from "./DrawnBar";
import { FigureSymbol } from "./FigureSymbol";
import { EXAMPLES_PAGE_SIZE, plural } from "./stats";

// Los ejemplos de una cifra de un corpus público (#424, ADR-0073), como el panel del informe
// local: dónde está cada uno, su compás dibujado desde los datos (nunca una imagen del corpus) y
// lo que leyó HOMR frente a lo correcto. Paginados, nunca con un «ver más».

/** El panel de los ejemplos: en una vista estrecha va debajo, y al elegir se lleva a la vista. */
export const EXAMPLES_ID = "homr-ejemplos";

export interface Selection {
  key: string;
  title: string;
  kicker: string;
}

/** Paginación como la del informe: «Anterior», los números de página y «Siguiente». En un
 * extremo, el paso queda con aria-disabled en vez de desactivarse: así no pierde el foco. */
export function Pager({
  label,
  page,
  pages,
  onPage,
}: {
  label: string;
  page: number;
  pages: number;
  onPage: (page: number) => void;
}) {
  if (pages < 2) return null;
  return (
    <nav className="homr__pager" aria-label={label}>
      <button
        type="button"
        className="homr__pager-step"
        aria-disabled={page === 0}
        onClick={() => {
          if (page > 0) onPage(page - 1);
        }}
      >
        Anterior
      </button>
      {Array.from({ length: pages }, (_, index) => (
        <button
          key={index}
          type="button"
          aria-current={index === page ? "page" : undefined}
          aria-label={`Página ${String(index + 1)} de ${String(pages)}`}
          onClick={() => {
            onPage(index);
          }}
        >
          {index + 1}
        </button>
      ))}
      <button
        type="button"
        className="homr__pager-step"
        aria-disabled={page === pages - 1}
        onClick={() => {
          if (page < pages - 1) onPage(page + 1);
        }}
      >
        Siguiente
      </button>
    </nav>
  );
}

function Token({
  text,
  beats,
  figures,
  className,
}: {
  text: string;
  beats: string;
  figures: Record<string, FigureRead>;
  className: string;
}) {
  return (
    <span className={`homr__tok ${className}`}>
      {beats && <FigureSymbol figure={figures[beats]} />}
      {text}
    </span>
  );
}

/** Lo que leyó HOMR frente a lo correcto, como en el informe. */
function Change({
  example,
  figures,
}: {
  example: HomrErrorExampleRead;
  figures: Record<string, FigureRead>;
}): ReactNode {
  const read = (
    <Token
      text={example.read}
      beats={example.read_beats}
      figures={figures}
      className="homr__tok--del"
    />
  );
  const fix = (
    <Token
      text={example.fix}
      beats={example.fix_beats}
      figures={figures}
      className="homr__tok--ins"
    />
  );
  if (example.kind === "extra") {
    return (
      <>
        <span className="label homr__muted">HOMR leyó de más</span>
        {read}
        <span className="homr__ex-note">No está en la partitura: se borró.</span>
      </>
    );
  }
  if (example.kind === "missing") {
    return (
      <>
        <span className="label homr__muted">HOMR no leyó</span>
        {fix}
      </>
    );
  }
  if (example.read === example.fix) {
    return <Token text={example.read} beats={example.read_beats} figures={figures} className="" />;
  }
  return (
    <>
      <span className="label homr__muted">HOMR</span>
      {read}
      <span className="label homr__muted">Correcto</span>
      {fix}
    </>
  );
}

export function ExamplesPanel({
  stats,
  selected,
  corpus,
}: {
  stats: HomrErrorStatsValuesRead;
  selected: Selection | null;
  corpus: string;
}) {
  const [page, setPage] = useState({ key: "", index: 0 });
  const ids = selected ? (stats.example_keys?.[selected.key] ?? []) : [];
  const examples = ids.flatMap((i) => {
    const example = stats.examples?.[i];
    return example ? [example] : [];
  });
  const pages = Math.ceil(examples.length / EXAMPLES_PAGE_SIZE);
  // Al elegir otra cifra, vuelve a la primera página.
  const current = page.key === selected?.key ? Math.min(page.index, pages - 1) : 0;
  const shown = examples.slice(current * EXAMPLES_PAGE_SIZE, (current + 1) * EXAMPLES_PAGE_SIZE);
  return (
    <aside className="homr__examples" aria-labelledby="homr-ex-title" id={EXAMPLES_ID}>
      <div className="homr__ex-head" aria-live="polite">
        <p className="label homr__muted">{selected?.kicker ?? "Ejemplos"}</p>
        <h3 id="homr-ex-title">{selected?.title ?? "Ejemplos"}</h3>
        <p className="homr__panel-note">
          {!selected
            ? "Elige una cifra, una barra, una columna o una casilla para ver sus ejemplos."
            : examples.length
              ? `${plural(examples.length, "ejemplo", "ejemplos")}${examples.length === 12 ? " (como mucho, 12)" : ""}. Cada compás lo dibuja Cadenza desde los datos de ${corpus} (Calvo-Zaragoza y Rizo, 2018), no es una imagen del corpus: arriba lo que leyó HOMR y abajo lo correcto, con la nota del ejemplo en violeta.`
              : "Ningún ejemplo de esta cifra."}
        </p>
      </div>
      {shown.length > 0 && (
        <ol className="homr__ex-list" role="list">
          {shown.map((example, index) => {
            const bar = example.bar ? stats.bars?.[example.bar] : undefined;
            return (
              <li key={`${String(current)}-${String(index)}`} className="homr__ex">
                {bar && (
                  <DrawnBar
                    bar={bar}
                    atRead={example.at_read}
                    atFix={example.at_fix}
                    measure={example.measure}
                    figures={stats.figures}
                  />
                )}
                <div className="homr__ex-text">
                  <p className="homr__ex-where">
                    {example.score} · compás {example.measure} · pentagrama {example.staff}
                  </p>
                  <p className="homr__ex-change">
                    <Change example={example} figures={stats.figures} />
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      <div className="homr__ex-pager">
        <Pager
          label="Páginas de los ejemplos"
          page={current}
          pages={pages}
          onPage={(index) => {
            if (selected) setPage({ key: selected.key, index });
          }}
        />
      </div>
    </aside>
  );
}
