import { useEffect, useState, type PointerEvent as ReactPointerEvent } from "react";
import { api } from "../../api/instance";
import { SiteHeader } from "../../components/SiteHeader";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type {
  ErrorRateRead,
  FigureRead,
  HomrErrorStatsRead,
  HomrErrorStatsValuesRead,
} from "../../types";
import { FigureSymbol } from "./FigureSymbol";
import "./homr-errors.css";
import {
  cadenzaPending,
  cellAlpha,
  DEFAULT_MIN_SESSIONS,
  durationMatrix,
  findings,
  fmt,
  type Finding,
  groupInfo,
  MIN_ACCOUNTS,
  opName,
  OUTCOMES,
  PAGE_SIZE,
  pct,
  perHundred,
  plural,
  REFRESH_MS,
  shownGroups,
  STRONG_ALPHA,
  stepName,
  whenText,
} from "./stats";

// La página pública con los errores de HOMR, en vivo (#424, `/errores-de-homr`): las cifras de
// conjunto que sirve `GET /stats/homr-errors` (#423, ADR-0073). Ni fotos ni nada de una partitura
// de usuario. Tiene su propia vista, enlazada desde la cabecera: no va en la portada. Se compone
// como el informe local (#418, `ml/informe_tablas.html`): bandas con su cabecera invertida, una
// barra fija con el grupo, paneles separados por filetes y un rótulo al pasar sobre cada cifra.

export type StatsLoader = (signal: AbortSignal) => Promise<HomrErrorStatsRead>;

const loadStats: StatsLoader = (signal) =>
  api.request<HomrErrorStatsRead>("/stats/homr-errors", { auth: false, signal });

interface StatsState {
  data: HomrErrorStatsRead | null;
  failed: boolean;
}

/** Las cifras, pedidas al entrar, cada `refreshMs` mientras la pestaña se ve y al volver a una
 * pestaña que lleva oculta más de eso. Un fallo deja las últimas que llegaron. */
function useHomrErrorStats(load: StatsLoader, refreshMs: number): StatsState {
  const [state, setState] = useState<StatsState>({ data: null, failed: false });
  useEffect(() => {
    let controller: AbortController | null = null;
    let lastFetch = 0;
    const fetchNow = () => {
      lastFetch = Date.now();
      controller?.abort();
      const current = new AbortController();
      controller = current;
      load(current.signal).then(
        (data) => {
          if (!current.signal.aborted) setState({ data, failed: false });
        },
        () => {
          if (!current.signal.aborted) setState((before) => ({ ...before, failed: true }));
        },
      );
    };
    fetchNow();
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden") fetchNow();
    }, refreshMs);
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastFetch >= refreshMs) {
        fetchNow();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      controller?.abort();
    };
  }, [load, refreshMs]);
  return state;
}

// --- El rótulo al pasar -------------------------------------------------------------------------

interface Tip {
  title: string;
  text: string;
  x: number;
  y: number;
}

/** Lo que dice el rótulo de un elemento: `data-tip-title` en negrita y `data-tip` detrás. Es
 * texto llano (React lo escapa) y repite lo que ya está escrito: solo es para el ratón. */
function tipProps(title: string, text: string) {
  return { "data-tip-title": title, "data-tip": text };
}

function useTip() {
  const [tip, setTip] = useState<Tip | null>(null);
  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.pointerType === "touch") return;
    const target = event.target instanceof Element ? event.target.closest("[data-tip]") : null;
    if (!target) {
      setTip(null);
      return;
    }
    setTip({
      title: target.getAttribute("data-tip-title") ?? "",
      text: target.getAttribute("data-tip") ?? "",
      x: event.clientX,
      y: event.clientY,
    });
  };
  const onPointerLeave = () => {
    setTip(null);
  };
  return { tip, onPointerMove, onPointerLeave };
}

function TipBox({ tip }: { tip: Tip | null }) {
  if (!tip) return null;
  // A la derecha y debajo del puntero, sin salirse de la ventana.
  const left = Math.max(8, Math.min(tip.x + 14, window.innerWidth - 308));
  return (
    <div className="homr__tip" aria-hidden="true" style={{ left, top: tip.y + 16 }}>
      {tip.title && <b>{tip.title}</b>}
      {tip.title && tip.text ? " · " : ""}
      {tip.text}
    </div>
  );
}

// --- La página ----------------------------------------------------------------------------------

export function HomrErrorsPage({
  load = loadStats,
  refreshMs = REFRESH_MS,
}: {
  load?: StatsLoader;
  refreshMs?: number;
}) {
  useDocumentTitle("Errores de HOMR");
  return (
    <>
      <SiteHeader showSections={false} />
      <HomrErrors load={load} refreshMs={refreshMs} />
    </>
  );
}

export function HomrErrors({
  load = loadStats,
  refreshMs = REFRESH_MS,
}: {
  load?: StatsLoader;
  refreshMs?: number;
}) {
  const { data, failed } = useHomrErrorStats(load, refreshMs);
  const [chosen, setChosen] = useState<string | null>(null);
  const { tip, onPointerMove, onPointerLeave } = useTip();
  const groups = data ? shownGroups(data) : [];
  const group = groups.find((g) => g.id === chosen) ?? groups[0];
  const stats = group?.stats ?? null;
  // El mínimo lo dice la API; si aún no hay cálculo, el de ADR-0073.
  const minSessions =
    data?.groups.find((g) => g.id === "cadenza")?.min_sessions ?? DEFAULT_MIN_SESSIONS;

  return (
    <main
      className="homr"
      aria-labelledby="homr-title"
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      <header className="homr__masthead">
        <div>
          <p className="label homr__muted">Cifras de conjunto · se actualizan solas</p>
          <h1 id="homr-title" className="homr__page-title">
            Errores de HOMR, en vivo
          </h1>
          <p className="homr__lead">
            Qué notas lee mal HOMR y cómo se corrigen: con las correcciones de quienes usan Cadenza
            y con un corpus público. Son cifras de conjunto: ninguna foto ni ninguna partitura de
            nadie.
          </p>
        </div>
        {data ? (
          <p className="homr__meta">
            {data.computed_at ? (
              <>
                Las de Cadenza, calculadas el{" "}
                <span className="homr__num">{whenText(data.computed_at)}</span>.
                <br />
                Se actualizan solas cada 5 minutos.
              </>
            ) : (
              "Las cifras de Cadenza aún no se han calculado. Se actualizan solas cada 5 minutos."
            )}
          </p>
        ) : (
          <p className="homr__meta" role="status">
            {failed
              ? "Ahora no se pueden cargar las cifras. Se vuelve a intentar en unos minutos."
              : "Cargando las cifras…"}
          </p>
        )}
        <div className="homr__about">
          <section aria-labelledby="homr-about-homr">
            <h2 id="homr-about-homr">HOMR</h2>
            <p>
              El programa de reconocimiento óptico de música (OMR) de código abierto que usa
              Cadenza: mira la imagen de una partitura y escribe sus notas, con redes neuronales de
              visión. <a href="https://github.com/liebharc/homr">github.com/liebharc/homr</a>
            </p>
          </section>
          <section aria-labelledby="homr-about-primus">
            <h2 id="homr-about-primus">PrIMuS y Camera-PrIMuS</h2>
            <p>
              «Printed Images of Music Staves» (Calvo-Zaragoza y Rizo, 2018): íncipits del catálogo
              RISM dibujados por ordenador, cada uno con su partitura correcta. Camera-PrIMuS son
              los mismos con las distorsiones de una foto. Su página no indica licencia: aquí se
              cita y solo salen sus cifras.{" "}
              <a href="https://grfia.dlsi.ua.es/primus/">grfia.dlsi.ua.es/primus</a>
            </p>
          </section>
          <section aria-labelledby="homr-about-cadenza">
            <h2 id="homr-about-cadenza">Cadenza</h2>
            <p>
              Las transcripciones que alguien dio por terminadas, de las cuentas del equipo y de las
              que dieron permiso para usar sus datos. Salen cuando hay al menos {minSessions}{" "}
              sesiones de {MIN_ACCOUNTS} cuentas distintas, para que no sean las cifras de una sola
              persona.
            </p>
          </section>
        </div>
      </header>

      {data && cadenzaPending(data) && (
        <div className="homr__notice">
          <h2 className="homr__notice-title">Aún no hay cifras de Cadenza</h2>
          <p>
            Hacen falta al menos {minSessions} transcripciones terminadas de {MIN_ACCOUNTS} cuentas
            distintas.
            {groups.length > 0
              ? ` Mientras, estas son las de ${groups.map((g) => groupInfo(g.id).name).join(" y ")}.`
              : ""}
          </p>
        </div>
      )}

      {data && groups.length === 0 && (
        <p className="homr__empty">Todavía no hay cifras que enseñar.</p>
      )}

      {group && stats && (
        <>
          <nav className="homr__filters" aria-label="Qué cifras se ven">
            <span className="label homr__muted">Cifras</span>
            <div className="homr__toggle" role="group" aria-label="Qué cifras se ven">
              {groups.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  aria-pressed={g.id === group.id}
                  onClick={() => {
                    setChosen(g.id);
                  }}
                >
                  {groupInfo(g.id).name}
                </button>
              ))}
            </div>
          </nav>
          <GroupStats
            key={group.id}
            name={groupInfo(group.id).name}
            about={groupInfo(group.id).about}
            sessions={group.sessions ?? stats.scores}
            source={group.source}
            computedAt={group.computed_at}
            stats={stats}
          />
        </>
      )}
      <TipBox tip={tip} />
    </main>
  );
}

function GroupStats({
  name,
  about,
  sessions,
  source,
  computedAt,
  stats,
}: {
  name: string;
  about: string;
  sessions: number;
  source: string;
  computedAt: string;
  stats: HomrErrorStatsValuesRead;
}) {
  const figures = stats.figures;
  const read = stats.read;
  const facts = findings(stats);
  const count =
    source === "corpus"
      ? plural(sessions, "íncipit", "íncipits")
      : plural(sessions, "transcripción", "transcripciones");
  return (
    <>
      <p className="homr__scope">
        <span className="homr__scope-name">{name}</span> ·{" "}
        <span className="homr__num">{count}</span>. {about}
        {source === "corpus" && (
          <span className="homr__muted">
            {" "}
            Calculadas una vez sobre el corpus, el {whenText(computedAt)}.
          </span>
        )}
      </p>

      <section className="homr__band" aria-labelledby="homr-findings">
        <div className="homr__head">
          <h2 id="homr-findings">Lo que dicen los datos</h2>
          <span className="homr__count">
            {name} · {count}
          </span>
        </div>
        {facts.length ? (
          <ul className="homr__findings" role="list">
            {facts.map((fact) => (
              <li key={fact.kicker} className="homr__finding">
                <span className="label homr__muted">{fact.kicker}</span>
                <b className="homr__big">{fact.big}</b>
                <span className="homr__finding-text">
                  <FindingText fact={fact} figures={figures} />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="homr__panel-note">Aún hay pocas notas para sacar conclusiones.</p>
        )}
        {stats.reordered > 0 && (
          <div className="homr__callout">
            <p>
              <strong>
                {plural(stats.reordered, "nota", "notas")} de acordes solo cambian de orden.
              </strong>{" "}
              HOMR las escribe en otro orden que la partitura correcta y la comparación lo vería
              como un error de altura: aquí no se cuentan.
            </p>
          </div>
        )}
      </section>

      <section className="homr__band" aria-labelledby="homr-tiles">
        <div className="homr__head">
          <h2 id="homr-tiles">Las cifras</h2>
        </div>
        <dl className="homr__tiles">
          {[
            [fmt(stats.scores), source === "corpus" ? "Íncipits" : "Transcripciones"],
            [fmt(read), "Notas y silencios leídos"],
            [pct(stats.outcome.bien ?? 0, read), "Bien leídos"],
            [fmt(stats.outcome.corregida ?? 0), "Corregidos"],
            [fmt(stats.outcome.borrada ?? 0), "Sobraban"],
            [fmt(stats.missing), "Que HOMR no leyó"],
          ].map(([value, label]) => (
            <div key={label} className="homr__tile">
              <dt className="label">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="homr__band" aria-labelledby="homr-charts">
        <div className="homr__head">
          <h2 id="homr-charts">Dónde y cómo falla</h2>
        </div>

        <section className="homr__panel" aria-labelledby="homr-outcome">
          <h3 id="homr-outcome">Qué pasó con cada nota leída</h3>
          <p className="homr__panel-note">
            Cada nota o silencio que leyó HOMR, comparado con la partitura correcta. Las notas que
            HOMR no leyó no están aquí: salen en «Qué se corrige».
          </p>
          <dl className="homr__defs">
            {OUTCOMES.map((outcome) => (
              <div key={outcome.key} className="homr__def">
                <dt>
                  <span className={`homr__swatch homr__part--${outcome.key}`} aria-hidden="true" />
                  <span className="label">{outcome.label}</span>
                </dt>
                <dd>{outcome.what}</dd>
              </div>
            ))}
          </dl>
          <OutcomeBar stats={stats} name={name} />
        </section>

        <div className="homr__pair">
          <section className="homr__panel" aria-labelledby="homr-ops">
            <h3 id="homr-ops">Qué se corrige</h3>
            <p className="homr__panel-note">
              Por cada 100 notas que leyó HOMR, cuántas correcciones de cada tipo hicieron falta.
            </p>
            <OpsBars ops={stats.ops} read={read} />
          </section>
          <section className="homr__panel" aria-labelledby="homr-steps">
            <h3 id="homr-steps">Cuánto se movió la altura</h3>
            <p className="homr__panel-note">
              En las correcciones de altura, cuántas líneas o espacios del pentagrama hay entre lo
              que leyó HOMR y lo correcto.
            </p>
            <StepsChart steps={stats.steps} />
          </section>
        </div>

        <section className="homr__panel" aria-labelledby="homr-where">
          <h3 id="homr-where">Dónde se equivoca más</h3>
          <p className="homr__panel-note">
            Qué parte de las notas tuvo alguna corrección, en grupos de 30 notas o más.
          </p>
          {stats.by_vs_key.length + stats.by_clef.length + stats.by_duration.length ? (
            <div className="homr__where">
              <RateList title="Alteración frente a la armadura" rows={stats.by_vs_key} />
              <RateList title="Clave" rows={stats.by_clef} />
              <RateList title="Figura leída" rows={stats.by_duration} figures={figures} />
            </div>
          ) : (
            <p className="homr__panel-note">Aún hay pocas notas para comparar.</p>
          )}
        </section>

        <section className="homr__panel" aria-labelledby="homr-durations">
          <h3 id="homr-durations">Figura leída y correcta</h3>
          <p className="homr__panel-note">
            En las correcciones de figura. Filas: la figura que leyó HOMR; columnas: la correcta.
            Cuanto más violeta, más casos.
          </p>
          <DurationTable durations={stats.durations} figures={figures} />
        </section>
      </section>
    </>
  );
}

/** La frase de un hallazgo; si habla de una figura, su símbolo va junto a su nombre. */
function FindingText({ fact, figures }: { fact: Finding; figures: Record<string, FigureRead> }) {
  const figure = fact.figure;
  const at = figure ? fact.text.indexOf(figure.label) : -1;
  if (!figure || at < 0) return <>{fact.text}</>;
  return (
    <>
      {fact.text.slice(0, at)}
      <span className="homr__nowrap">
        <FigureSymbol figure={figures[figure.beats]} />
        {figure.label}
      </span>
      {fact.text.slice(at + figure.label.length)}
    </>
  );
}

/** Qué pasó con cada nota: una barra al 100 %, por patrón, con su parte escrita donde cabe. */
function OutcomeBar({ stats, name }: { stats: HomrErrorStatsValuesRead; name: string }) {
  const read = stats.read;
  if (!read) return null;
  return (
    <div className="homr__stack-row">
      <span className="homr__stack-name">{name}</span>
      <div className="homr__stack">
        {OUTCOMES.map((outcome) => {
          const n = stats.outcome[outcome.key] ?? 0;
          if (!n) return null;
          const share = n / read;
          const solid = outcome.key === "corregida" || outcome.key === "bien";
          return (
            <span
              key={outcome.key}
              className={`homr__stack-part homr__part--${outcome.key}`}
              style={{ flexGrow: n }}
              {...tipProps(outcome.label, `${fmt(n)} (${pct(n, read)})`)}
            >
              {solid && share >= 0.08 && <span className="homr__stack-text">{pct(n, read)}</span>}
              <span className="visually-hidden">
                {outcome.label}: {fmt(n)} ({pct(n, read)})
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function OpsBars({ ops, read }: { ops: Record<string, number>; read: number }) {
  const rows = Object.entries(ops)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (!read || !rows.length) return <p className="homr__panel-note">Sin correcciones.</p>;
  const top = Math.max(...rows.map(([, n]) => n));
  return (
    <ul className="homr__bars" role="list">
      {rows.map(([op, n]) => {
        const per100 = perHundred(n, read);
        return (
          <li
            key={op}
            className="homr__bar"
            {...tipProps(opName(op), `${fmt(n)} correcciones, ${per100} por cada 100 notas`)}
          >
            <span className="homr__bar-name">{opName(op)}</span>
            <span className="homr__bar-track" aria-hidden="true">
              <span className="homr__bar-fill" style={{ width: `${String((100 * n) / top)}%` }} />
            </span>
            <span className="homr__bar-value">
              {per100}
              <span className="visually-hidden"> por cada 100 notas ({fmt(n)} correcciones)</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

const STEPS = Array.from({ length: 17 }, (_, i) => i - 8);

function StepsChart({ steps }: { steps: Record<string, number> }) {
  const total = Object.values(steps).reduce((a, b) => a + b, 0);
  if (!total) return <p className="homr__panel-note">Sin correcciones de altura.</p>;
  const top = Math.max(1, ...Object.values(steps));
  return (
    <figure className="homr__steps">
      <ol className="homr__steps-cols" role="list">
        {STEPS.map((step) => {
          const n = steps[String(step)] ?? 0;
          if (!n) return <li key={step} className="homr__steps-col" aria-hidden="true" />;
          return (
            <li
              key={step}
              className="homr__steps-col homr__steps-col--data"
              {...tipProps(stepName(step), `${fmt(n)} (${pct(n, total)})`)}
            >
              <span
                className="homr__steps-fill"
                style={{ height: `${String((100 * n) / top)}%` }}
                aria-hidden="true"
              />
              <span className="visually-hidden">
                {stepName(step)}: {fmt(n)} ({pct(n, total)})
              </span>
            </li>
          );
        })}
      </ol>
      <div className="homr__steps-axis" aria-hidden="true">
        {STEPS.map((step) => (
          <span key={step} className={step === 0 ? "homr__steps-zero" : undefined}>
            {step > 0 ? `+${String(step)}` : String(step)}
          </span>
        ))}
      </div>
      <figcaption className="homr__steps-caption label">
        <span>Más abajo</span>
        <span>Más arriba</span>
      </figcaption>
    </figure>
  );
}

function RateList({
  title,
  rows,
  figures,
}: {
  title: string;
  rows: ErrorRateRead[];
  figures?: Record<string, FigureRead>;
}) {
  const [page, setPage] = useState(0);
  if (!rows.length) return null;
  const pages = Math.ceil(rows.length / PAGE_SIZE);
  const current = Math.min(page, pages - 1);
  const shown = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);
  return (
    <div className="homr__rates">
      <h4 className="label homr__muted homr__rates-title">{title}</h4>
      <ul className="homr__bars" role="list">
        {shown.map((row) => (
          <li
            key={row.key}
            className="homr__bar"
            {...tipProps(row.label, `${fmt(row.wrong)} de ${fmt(row.n)} notas con corrección`)}
          >
            <span className="homr__bar-name">
              <span className="homr__bar-label">
                {figures && <FigureSymbol figure={figures[row.key.slice("readdur:".length)]} />}
                {row.label}
              </span>
              <span className="homr__bar-sub">
                {fmt(row.wrong)} de {fmt(row.n)} notas
              </span>
            </span>
            <span className="homr__bar-track" aria-hidden="true">
              <span className="homr__bar-fill" style={{ width: `${String(100 * row.rate)}%` }} />
            </span>
            <span className="homr__bar-value">{pct(row.wrong, row.n, 0)}</span>
          </li>
        ))}
      </ul>
      {pages > 1 && (
        <nav className="homr__pager" aria-label={`Páginas de «${title}»`}>
          <button
            type="button"
            className="homr__pager-step"
            aria-disabled={current === 0}
            onClick={() => {
              if (current > 0) setPage(current - 1);
            }}
          >
            Anterior
          </button>
          {Array.from({ length: pages }, (_, index) => (
            <button
              key={index}
              type="button"
              aria-current={index === current ? "page" : undefined}
              aria-label={`Página ${String(index + 1)} de ${String(pages)}`}
              onClick={() => {
                setPage(index);
              }}
            >
              {index + 1}
            </button>
          ))}
          <button
            type="button"
            className="homr__pager-step"
            aria-disabled={current === pages - 1}
            onClick={() => {
              if (current < pages - 1) setPage(current + 1);
            }}
          >
            Siguiente
          </button>
        </nav>
      )}
    </div>
  );
}

function DurationTable({
  durations,
  figures,
}: {
  durations: HomrErrorStatsValuesRead["durations"];
  figures: Record<string, FigureRead>;
}) {
  if (!durations.length) return <p className="homr__panel-note">Sin correcciones de figura.</p>;
  const matrix = durationMatrix(durations);
  return (
    <div className="homr__scroll" role="region" aria-label="Figura leída y correcta" tabIndex={0}>
      <table className="homr__matrix">
        <thead>
          <tr>
            <th className="homr__corner" rowSpan={2} scope="col">
              Leída, por filas
              <br />
              Correcta, por columnas
            </th>
            {matrix.fixes.map((fix) => (
              <th key={fix} className="homr__matrix-name" scope="col">
                {matrix.names[fix]}
              </th>
            ))}
          </tr>
          <tr>
            {matrix.fixes.map((fix) => (
              <th key={fix} className="homr__matrix-sym" aria-hidden="true">
                <FigureSymbol figure={figures[fix]} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.reads.map((readBeats) => (
            <tr key={readBeats}>
              <th scope="row">
                <FigureSymbol figure={figures[readBeats]} />
                {matrix.names[readBeats]}
              </th>
              {matrix.fixes.map((fix) => {
                const n = matrix.count(readBeats, fix);
                if (!n) return <td key={fix} />;
                const alpha = cellAlpha(n, matrix.max);
                const share = Math.round(alpha * 100);
                return (
                  <td
                    key={fix}
                    className={
                      alpha >= STRONG_ALPHA ? "homr__cell homr__cell--strong" : "homr__cell"
                    }
                    style={{
                      backgroundColor: `color-mix(in srgb, var(--color-accent) ${String(share)}%, var(--color-paper))`,
                    }}
                    {...tipProps(
                      `Leída ${matrix.names[readBeats] ?? ""}, correcta ${matrix.names[fix] ?? ""}`,
                      fmt(n),
                    )}
                  >
                    {fmt(n)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
