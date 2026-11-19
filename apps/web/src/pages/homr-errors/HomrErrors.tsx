import { useEffect, useState } from "react";
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
  durationMatrix,
  findings,
  fmt,
  groupInfo,
  opName,
  OUTCOMES,
  PAGE_SIZE,
  pct,
  perHundred,
  plural,
  REFRESH_MS,
  shownGroups,
  stepName,
  whenText,
} from "./stats";

// La página pública con los errores de HOMR, en vivo (#424, `/errores-de-homr`): las cifras de
// conjunto que sirve `GET /stats/homr-errors` (#423, ADR-0073). Ni fotos ni nada de una partitura
// de usuario. Tiene su propia vista, enlazada desde la cabecera: no va en la portada.

export type StatsLoader = (signal: AbortSignal) => Promise<HomrErrorStatsRead>;

const loadStats: StatsLoader = (signal) =>
  api.request<HomrErrorStatsRead>("/stats/homr-errors", { auth: false, signal });

interface StatsState {
  data: HomrErrorStatsRead | null;
  failed: boolean;
}

/** Las cifras, pedidas al entrar y cada `refreshMs` mientras la pestaña se ve. Un fallo deja
 * las últimas que llegaron. */
function useHomrErrorStats(load: StatsLoader, refreshMs: number): StatsState {
  const [state, setState] = useState<StatsState>({ data: null, failed: false });
  useEffect(() => {
    let controller: AbortController | null = null;
    const fetchNow = () => {
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
    return () => {
      window.clearInterval(timer);
      controller?.abort();
    };
  }, [load, refreshMs]);
  return state;
}

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
  const groups = data ? shownGroups(data) : [];
  const group = groups.find((g) => g.id === chosen) ?? groups[0];
  const stats = group?.stats ?? null;

  return (
    <main className="homr" aria-labelledby="homr-title">
      <div className="homr__intro">
        <h1 id="homr-title" className="homr__page-title">
          Errores de HOMR, en vivo
        </h1>
        <p className="homr__lead">
          Qué notas lee mal HOMR y cómo se corrigen: con las correcciones de quienes usan Cadenza y
          con un corpus público. Son cifras de conjunto: ninguna foto ni ninguna partitura de nadie.
        </p>
        <p className="homr__when" aria-live="polite">
          {data?.computed_at
            ? `Calculadas el ${whenText(data.computed_at)}. Se actualizan solas cada 5 minutos.`
            : data
              ? "Las cifras de Cadenza aún no se han calculado. Se actualizan solas cada 5 minutos."
              : failed
                ? "Ahora no se pueden cargar las cifras. Se vuelve a intentar en unos minutos."
                : "Cargando las cifras…"}
        </p>
      </div>
      <div className="homr__about">
        <section aria-labelledby="homr-about-homr">
          <h2 id="homr-about-homr" className="homr__about-title">
            HOMR
          </h2>
          <p>
            El programa de reconocimiento óptico de música (OMR) de código abierto que usa Cadenza:
            mira la imagen de una partitura y escribe sus notas, con redes neuronales de visión.{" "}
            <a href="https://github.com/liebharc/homr">github.com/liebharc/homr</a>
          </p>
        </section>
        <section aria-labelledby="homr-about-primus">
          <h2 id="homr-about-primus" className="homr__about-title">
            PrIMuS y Camera-PrIMuS
          </h2>
          <p>
            «Printed Images of Music Staves» (Calvo-Zaragoza y Rizo, 2018): íncipits del catálogo
            RISM dibujados por ordenador, cada uno con su partitura correcta. Camera-PrIMuS son los
            mismos con las distorsiones de una foto. Su página no indica licencia: aquí se cita y
            solo salen sus cifras.{" "}
            <a href="https://grfia.dlsi.ua.es/primus/">grfia.dlsi.ua.es/primus</a>
          </p>
        </section>
        <section aria-labelledby="homr-about-cadenza">
          <h2 id="homr-about-cadenza" className="homr__about-title">
            Cadenza
          </h2>
          <p>
            Las transcripciones que alguien dio por terminadas, de las cuentas del equipo y de las
            que dieron permiso para usar sus datos. Salen cuando hay al menos 5 sesiones de 3
            cuentas distintas, para que no sean las cifras de una sola persona.
          </p>
        </section>
      </div>

      {data && cadenzaPending(data) && (
        <div className="homr__notice">
          <h2 className="homr__notice-title">Aún no hay cifras de Cadenza</h2>
          <p>
            Hacen falta al menos 5 transcripciones terminadas de 3 cuentas distintas.
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
          {groups.length > 1 && (
            <div className="homr__groups" role="group" aria-label="Qué cifras se ven">
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
          )}
          <GroupStats
            name={groupInfo(group.id).name}
            about={groupInfo(group.id).about}
            sessions={group.sessions ?? stats.scores}
            source={group.source}
            stats={stats}
          />
        </>
      )}
    </main>
  );
}

function GroupStats({
  name,
  about,
  sessions,
  source,
  stats,
}: {
  name: string;
  about: string;
  sessions: number;
  source: string;
  stats: HomrErrorStatsValuesRead;
}) {
  const figures = stats.figures;
  const read = stats.read;
  const facts = findings(stats);
  return (
    <div className="homr__group">
      <p className="homr__scope">
        <span className="label">{name}</span>{" "}
        <span className="homr__scope-count">
          {source === "corpus"
            ? plural(sessions, "íncipit", "íncipits")
            : plural(sessions, "transcripción", "transcripciones")}
        </span>{" "}
        {about}
      </p>

      <section className="homr__block" aria-labelledby="homr-findings">
        <h2 id="homr-findings" className="homr__title">
          Lo que dicen los datos
        </h2>
        {facts.length ? (
          <ul className="homr__findings" role="list">
            {facts.map((fact) => (
              <li key={fact.kicker} className="homr__finding">
                <span className="label homr__kicker">{fact.kicker}</span>
                <span className="homr__big">{fact.big}</span>
                <span className="homr__finding-text">
                  {fact.figure && <FigureSymbol figure={figures[fact.figure]} />}
                  {fact.text}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="homr__small">Aún hay pocas notas para sacar conclusiones.</p>
        )}
        {stats.reordered > 0 && (
          <p className="homr__small">
            {plural(stats.reordered, "nota", "notas")} de acordes que HOMR escribe en otro orden que
            la partitura correcta no cuentan como corrección: la comparación lo vería como un error
            de altura, y no lo es.
          </p>
        )}
      </section>

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

      <section className="homr__block" aria-labelledby="homr-outcome">
        <h2 id="homr-outcome" className="homr__title">
          Qué pasó con cada nota leída
        </h2>
        <p className="homr__small">
          Cada nota o silencio que leyó HOMR, comparado con la partitura correcta. Las notas que
          HOMR no leyó no están aquí: salen en «Qué se corrige».
        </p>
        <div className="homr__stack" aria-hidden="true">
          {OUTCOMES.map((outcome) => {
            const n = stats.outcome[outcome.key] ?? 0;
            return n ? (
              <span
                key={outcome.key}
                className={`homr__stack-part homr__stack-part--${outcome.key}`}
                style={{ flexGrow: n }}
              />
            ) : null;
          })}
        </div>
        <dl className="homr__outcomes">
          {OUTCOMES.map((outcome) => {
            const n = stats.outcome[outcome.key] ?? 0;
            return (
              <div key={outcome.key} className="homr__outcome">
                <dt>
                  <span
                    className={`homr__swatch homr__stack-part--${outcome.key}`}
                    aria-hidden="true"
                  />
                  <span className="label">{outcome.label}</span>
                  <span className="homr__number">
                    {fmt(n)} · {pct(n, read)}
                  </span>
                </dt>
                <dd>{outcome.what}</dd>
              </div>
            );
          })}
        </dl>
      </section>

      <div className="homr__pair">
        <section className="homr__block" aria-labelledby="homr-ops">
          <h2 id="homr-ops" className="homr__title">
            Qué se corrige
          </h2>
          <p className="homr__small">
            Por cada 100 notas que leyó HOMR, cuántas correcciones de cada tipo hicieron falta.
          </p>
          <OpsBars ops={stats.ops} read={read} />
        </section>
        <section className="homr__block" aria-labelledby="homr-steps">
          <h2 id="homr-steps" className="homr__title">
            Cuánto se movió la altura
          </h2>
          <p className="homr__small">
            En las correcciones de altura, cuántas líneas o espacios del pentagrama hay entre lo que
            leyó HOMR y lo correcto.
          </p>
          <StepsChart steps={stats.steps} />
        </section>
      </div>

      <section className="homr__block" aria-labelledby="homr-where">
        <h2 id="homr-where" className="homr__title">
          Dónde se equivoca más
        </h2>
        <p className="homr__small">
          Qué parte de las notas tuvo alguna corrección, en grupos de 30 notas o más.
        </p>
        {stats.by_vs_key.length + stats.by_clef.length + stats.by_duration.length ? (
          <div className="homr__where">
            <RateList title="Alteración frente a la armadura" rows={stats.by_vs_key} />
            <RateList title="Clave" rows={stats.by_clef} />
            <RateList title="Figura leída" rows={stats.by_duration} figures={figures} />
          </div>
        ) : (
          <p className="homr__small">Aún hay pocas notas para comparar.</p>
        )}
      </section>

      <section className="homr__block" aria-labelledby="homr-durations">
        <h2 id="homr-durations" className="homr__title">
          Figura leída y correcta
        </h2>
        <p className="homr__small">
          En las correcciones de figura. Filas: la figura que leyó HOMR; columnas: la correcta.
          Cuanto más violeta, más casos.
        </p>
        <DurationTable durations={stats.durations} figures={figures} />
      </section>
    </div>
  );
}

function OpsBars({ ops, read }: { ops: Record<string, number>; read: number }) {
  const rows = Object.entries(ops)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (!read || !rows.length) return <p className="homr__small">Sin correcciones.</p>;
  const top = Math.max(...rows.map(([, n]) => n));
  return (
    <ul className="homr__bars" role="list">
      {rows.map(([op, n]) => {
        const per100 = perHundred(n, read);
        return (
          <li key={op} className="homr__bar">
            <span className="homr__bar-name">{opName(op)}</span>
            <span className="homr__bar-track" aria-hidden="true">
              <span className="homr__bar-fill" style={{ width: `${String((100 * n) / top)}%` }} />
            </span>
            <span className="homr__number">
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
  if (!total) return <p className="homr__small">Sin correcciones de altura.</p>;
  const top = Math.max(1, ...Object.values(steps));
  return (
    <figure className="homr__steps">
      <ol className="homr__steps-cols" role="list">
        {STEPS.map((step) => {
          const n = steps[String(step)] ?? 0;
          return (
            <li key={step} className="homr__steps-col">
              <span
                className="homr__steps-fill"
                style={{ height: `${String((100 * n) / top)}%` }}
                aria-hidden="true"
              />
              {n > 0 && (
                <span className="visually-hidden">
                  {stepName(step)}: {fmt(n)} ({pct(n, total)})
                </span>
              )}
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
        <span>← Más abajo</span>
        <span>Más arriba →</span>
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
      <h3 className="label homr__rates-title">{title}</h3>
      <ul className="homr__bars" role="list">
        {shown.map((row) => (
          <li key={row.key} className="homr__bar">
            <span className="homr__bar-name">
              {figures && <FigureSymbol figure={figures[row.key.slice("readdur:".length)]} />}
              {row.label}
              <span className="homr__bar-sub">
                {fmt(row.wrong)} de {fmt(row.n)} notas
              </span>
            </span>
            <span className="homr__bar-track" aria-hidden="true">
              <span className="homr__bar-fill" style={{ width: `${String(100 * row.rate)}%` }} />
            </span>
            <span className="homr__number">{pct(row.wrong, row.n, 0)}</span>
          </li>
        ))}
      </ul>
      {pages > 1 && (
        <nav className="homr__pager" aria-label={`Páginas de «${title}»`}>
          <button
            type="button"
            className="button homr__pager-button"
            disabled={current === 0}
            onClick={() => {
              setPage(current - 1);
            }}
          >
            Anterior
          </button>
          <span className="homr__pager-text" aria-live="polite">
            Página {current + 1} de {pages}
          </span>
          <button
            type="button"
            className="button homr__pager-button"
            disabled={current === pages - 1}
            onClick={() => {
              setPage(current + 1);
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
  if (!durations.length) return <p className="homr__small">Sin correcciones de figura.</p>;
  const matrix = durationMatrix(durations);
  return (
    <div className="homr__scroll" role="region" aria-label="Figura leída y correcta" tabIndex={0}>
      <table className="homr__matrix">
        <thead>
          <tr>
            <th scope="col" className="homr__corner">
              <span className="label">Leída ↓ Correcta →</span>
            </th>
            {matrix.fixes.map((fix) => (
              <th key={fix} scope="col">
                <FigureSymbol figure={figures[fix]} />
                <span className="homr__matrix-name">{matrix.names[fix]}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.reads.map((readBeats) => (
            <tr key={readBeats}>
              <th scope="row">
                <FigureSymbol figure={figures[readBeats]} />
                <span className="homr__matrix-name">{matrix.names[readBeats]}</span>
              </th>
              {matrix.fixes.map((fix) => {
                const n = matrix.count(readBeats, fix);
                if (!n) return <td key={fix} />;
                const alpha = cellAlpha(n, matrix.max);
                return (
                  <td
                    key={fix}
                    className={alpha > 0.55 ? "homr__cell homr__cell--strong" : "homr__cell"}
                    style={{ backgroundColor: `rgb(122 44 240 / ${alpha.toFixed(2)})` }}
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
