import { useState, type ReactNode } from "react";
import type { FigureRead, HomrErrorExampleRead } from "../../types";
import { EngravedBar } from "./EngravedBar";
import { FigureSymbol } from "./FigureSymbol";
import type { ExamplesContent, Selection } from "./selection";
import { EXAMPLES_PAGE_SIZE, fmt, pageList, plural } from "./stats";

// Los ejemplos de una cifra o de una partitura del historial de un corpus público (#424,
// ADR-0073), como el panel del informe local: dónde está cada uno, su compás dibujado desde los
// datos (nunca una imagen del corpus) y lo que leyó HOMR frente a lo correcto. Paginados, nunca
// con un «ver más».

/** El panel de los ejemplos: en una vista estrecha va debajo, y al elegir se lleva a la vista. */
export const EXAMPLES_ID = "homr-ejemplos";

/** Un texto con sus cifras en Hanken Grotesk: en el bitmap, un 5 se confunde con un 8 (#418). */
export function WithNumbers({ text }: { text: string }) {
  const parts = text.split(/(\d+(?:[.,]\d+)?)/);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <span key={index} className="homr__num">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}

/** Paginación como la del informe: «Anterior», los números de página (con «…» si son muchas) y
 * «Siguiente». En un extremo, el paso queda con aria-disabled en vez de desactivarse: así no
 * pierde el foco. */
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
      {pageList(page, pages).map((index, at) =>
        index === null ? (
          <span key={`hueco-${String(at)}`} className="homr__pager-gap" aria-hidden="true">
            …
          </span>
        ) : (
          <button
            key={index}
            type="button"
            aria-current={index === page ? "page" : undefined}
            aria-label={`Página ${String(index + 1)} de ${String(pages)}`}
            onClick={() => {
              onPage(index);
            }}
          >
            {fmt(index + 1)}
          </button>
        ),
      )}
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
  content,
  selected,
  corpus,
}: {
  content: ExamplesContent;
  selected: Selection | null;
  corpus: string;
}) {
  const [page, setPage] = useState(0);
  const { examples, bars, figures } = content;
  const imageOf = content.imageOf ?? (() => null);
  const withImages = examples.some((example) => imageOf(example) !== null);
  const pages = Math.ceil(examples.length / EXAMPLES_PAGE_SIZE);
  // Cada cifra elegida monta el panel de nuevo (`key`): empieza en la primera página.
  const current = Math.min(page, Math.max(0, pages - 1));
  const shown = examples.slice(current * EXAMPLES_PAGE_SIZE, (current + 1) * EXAMPLES_PAGE_SIZE);
  return (
    <section className="homr__examples" aria-labelledby="homr-ex-title" id={EXAMPLES_ID}>
      <div className="homr__ex-head">
        <p className="label homr__muted">{selected?.kicker ?? "Ejemplos"}</p>
        <h3 id="homr-ex-title" aria-live="polite" tabIndex={-1}>
          <WithNumbers text={selected?.title ?? "Ejemplos"} />
        </h3>
        <p className="homr__panel-note">
          {examples.length
            ? `${plural(examples.length, "ejemplo", "ejemplos")}. ${
                withImages
                  ? `Arriba, la imagen del íncipit en ${corpus} (Calvo-Zaragoza y Rizo, 2018); debajo, su compás grabado por Cadenza desde los datos`
                  : `Cada compás lo graba Cadenza desde los datos de ${corpus} (Calvo-Zaragoza y Rizo, 2018)`
              }: arriba lo que leyó HOMR y abajo lo correcto, con la nota del ejemplo en violeta.`
            : content.empty}
        </p>
        {content.retry && (
          <button type="button" className="homr__retry" onClick={content.retry}>
            Volver a intentarlo
          </button>
        )}
      </div>
      {shown.length > 0 && (
        <ol className="homr__ex-list" role="list">
          {shown.map((example, index) => {
            const bar = example.bar ? bars[example.bar] : undefined;
            const image = imageOf(example);
            return (
              <li key={`${String(current)}-${String(index)}`} className="homr__ex">
                {image && (
                  <div className="homr__ex-photo">
                    <img
                      src={image}
                      alt={`El íncipit ${example.score} en ${corpus}`}
                      loading="lazy"
                      decoding="async"
                    />
                  </div>
                )}
                {bar && (
                  <EngravedBar
                    bar={bar}
                    atRead={example.at_read}
                    atFix={example.at_fix}
                    measure={example.measure}
                    figures={figures}
                  />
                )}
                <div className="homr__ex-text">
                  <p className="homr__ex-where">
                    {example.score} · compás {example.measure} · pentagrama {example.staff}
                  </p>
                  <p className="homr__ex-change">
                    <Change example={example} figures={figures} />
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      <div className="homr__ex-pager">
        <Pager label="Páginas de los ejemplos" page={current} pages={pages} onPage={setPage} />
      </div>
    </section>
  );
}
