import {
  memo,
  useEffect,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { api } from "../../api/instance";
import { SiteHeader } from "../../components/SiteHeader";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type {
  ErrorRateRead,
  FigureRead,
  HomrErrorStatsRead,
  HomrErrorStatsValuesRead,
} from "../../types";
import { EXAMPLES_ID, ExamplesPanel, Pager } from "./Examples";
import { FigureSymbol } from "./FigureSymbol";
import { HistoryPanel, ScoreExamples } from "./History";
import {
  figureExamples,
  loadScore as loadScoreDetail,
  SCORE_PREFIX,
  type ScoreLoader,
  type Selection,
} from "./selection";
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
  isBarline,
  opName,
  OUTCOMES,
  PAGE_SIZE,
  pct,
  perHundred,
  plural,
  shownGroups,
  STRONG_ALPHA,
  stepName,
  whenText,
} from "./stats";

// La página pública con los errores de HOMR (#424, `/errores-de-homr`): las cifras de conjunto
// que sirve `GET /stats/homr-errors` (#423, ADR-0073), pedidas una vez al entrar. No se presenta
// como algo en vivo (#453): las pruebas con público se hacen una vez y los corpus se calculan una
// vez. Ni fotos ni nada de una partitura
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

/** Las cifras, pedidas una vez al entrar. Si fallan, `retry` las vuelve a pedir. */
function useHomrErrorStats(load: StatsLoader): StatsState & { retry: () => void } {
  const [state, setState] = useState<StatsState>({ data: null, failed: false });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ data, failed: false });
      },
      () => {
        if (!controller.signal.aborted) setState((before) => ({ ...before, failed: true }));
      },
    );
    return () => {
      controller.abort();
    };
  }, [load, attempt]);
  return {
    ...state,
    retry: () => {
      setState((before) => ({ ...before, failed: false }));
      setAttempt((n) => n + 1);
    },
  };
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
  loadScore = loadScoreDetail,
}: {
  load?: StatsLoader;
  loadScore?: ScoreLoader;
}) {
  useDocumentTitle("Errores de HOMR");
  return (
    <>
      <SiteHeader showSections={false} />
      <HomrErrors load={load} loadScore={loadScore} />
    </>
  );
}

export function HomrErrors({
  load = loadStats,
  loadScore = loadScoreDetail,
}: {
  load?: StatsLoader;
  loadScore?: ScoreLoader;
}) {
  const { data, failed, retry } = useHomrErrorStats(load);
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
          <p className="label homr__muted">Cifras de conjunto</p>
          <h1 id="homr-title" className="homr__page-title">
            Errores de HOMR
          </h1>
          <p className="homr__lead">
            Qué notas lee mal HOMR y cómo se corrigen: con las correcciones de quienes usan Cadenza
            y con un corpus público. De Cadenza salen solo cifras de conjunto, nunca una foto ni una
            partitura de nadie; del corpus, también ejemplos con su imagen y su compás dibujado.
          </p>
        </div>
        {data ? (
          <p className="homr__meta">
            {data.computed_at ? (
              <>
                Las de Cadenza, calculadas el{" "}
                <span className="homr__num">{whenText(data.computed_at)}</span>.
              </>
            ) : (
              "Las cifras de Cadenza aún no se han calculado."
            )}
          </p>
        ) : (
          <div className="homr__meta" role="status">
            {failed ? (
              <>
                <p>Ahora no se pueden cargar las cifras.</p>
                <button type="button" className="homr__retry" onClick={retry}>
                  Volver a intentarlo
                </button>
              </>
            ) : (
              <p>Cargando las cifras…</p>
            )}
          </div>
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
              los mismos con las distorsiones de una foto. Aquí se citan: salen sus cifras y, de
              ejemplo, sus imágenes con el compás redibujado desde sus datos.{" "}
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
            <div className="homr__toggle" role="group">
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
            id={group.id}
            loadScore={loadScore}
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

/** Si la vista es estrecha: el panel de los ejemplos va debajo y hay que llevarlo a la vista. */
function narrowView(): boolean {
  try {
    return window.matchMedia("(max-width: 1180px)").matches;
  } catch {
    return false;
  }
}

/** Una cifra que se puede elegir para ver sus ejemplos (solo en los corpus); si no, un bloque. */
function Choice({
  selection,
  selected,
  onChoose,
  className,
  tip,
  label,
  children,
}: {
  selection: Selection | null;
  selected: Selection | null;
  onChoose: ((selection: Selection) => void) | null;
  className: string;
  tip?: Record<string, string>;
  /** El nombre del botón, si su texto no basta (una casilla de la matriz es solo un número). */
  label?: string;
  children: ReactNode;
}) {
  if (!onChoose || !selection) {
    return (
      <div className={className} {...tip}>
        {children}
      </div>
    );
  }
  return (
    <button
      type="button"
      className={`${className} homr__choice`}
      aria-current={selected?.key === selection.key ? "true" : undefined}
      aria-label={label}
      onClick={() => {
        onChoose(selection);
      }}
      {...tip}
    >
      {children}
    </button>
  );
}

interface Choosing {
  selected: Selection | null;
  onChoose: ((selection: Selection) => void) | null;
}

const GroupStats = memo(function GroupStats({
  id,
  loadScore,
  name,
  about,
  sessions,
  source,
  computedAt,
  stats,
}: {
  id: string;
  loadScore: ScoreLoader;
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
  const withExamples = source === "corpus" && Boolean(stats.example_keys);
  // El historial, solo de los corpus: de Cadenza no sale nada de una transcripción concreta.
  const history = withExamples ? (stats.history ?? null) : null;
  // Como en el informe, al empezar se ven los ejemplos de lo primero que dicen los datos.
  const [selected, setSelected] = useState<Selection | null>(() => {
    const first = withExamples ? facts.find((fact) => fact.key) : undefined;
    return first?.key ? { key: first.key, title: first.title ?? "", kicker: first.kicker } : null;
  });
  const onChoose = withExamples
    ? (selection: Selection) => {
        setSelected(selection);
        if (narrowView()) document.getElementById(EXAMPLES_ID)?.scrollIntoView({ block: "start" });
      }
    : null;
  const choosing: Choosing = { selected, onChoose };
  const count =
    source === "corpus"
      ? plural(sessions, "íncipit", "íncipits")
      : plural(sessions, "transcripción", "transcripciones");

  const charts = (
    <>
      <section className="homr__panel" aria-labelledby="homr-outcome">
        <h3 id="homr-outcome">Qué pasó con cada nota leída</h3>
        <p className="homr__panel-note">
          Cada nota o silencio que leyó HOMR, comparado con la partitura correcta en orden, de
          principio a fin. Las notas que HOMR no leyó no están aquí: salen en «Qué se corrige». Si
          HOMR no leyó una barra de compás, las notas de los dos lados siguen bien leídas: lo que
          falta es la barra, que también sale en «Qué se corrige».
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
            Por cada 100 notas que leyó HOMR, cuántas correcciones de cada tipo hicieron falta y
            cuántas barras de compás leyó mal.
          </p>
          <OpsBars ops={stats.ops} read={read} choosing={choosing} />
        </section>
        <section className="homr__panel" aria-labelledby="homr-steps">
          <h3 id="homr-steps">Cuánto se movió la altura</h3>
          <p className="homr__panel-note">
            En las correcciones de altura, cuántas líneas o espacios del pentagrama hay entre lo que
            leyó HOMR y lo correcto.
          </p>
          <StepsChart steps={stats.steps} choosing={choosing} />
        </section>
      </div>

      <section className="homr__panel" aria-labelledby="homr-where">
        <h3 id="homr-where">Dónde se equivoca más</h3>
        <p className="homr__panel-note">
          Qué parte de las notas tuvo alguna corrección, en grupos de 30 notas o más.
        </p>
        {stats.by_vs_key.length + stats.by_clef.length + stats.by_duration.length ? (
          <div className="homr__where">
            <RateList
              title="Alteración frente a la armadura"
              rows={stats.by_vs_key}
              choosing={choosing}
            />
            <RateList title="Clave" rows={stats.by_clef} choosing={choosing} />
            <RateList
              title="Figura leída"
              rows={stats.by_duration}
              figures={figures}
              choosing={choosing}
            />
          </div>
        ) : (
          <p className="homr__panel-note">Aún hay pocas notas para comparar.</p>
        )}
      </section>

      <section className="homr__panel" aria-labelledby="homr-durations">
        <h3 id="homr-durations">Figura leída y correcta</h3>
        <p className="homr__panel-note">
          En las correcciones de figura. Cada fila es la figura que leyó HOMR y cada columna, la que
          era: la casilla dice cuántas veces pasó, y cuanto más violeta, más.
          {stats.durations[0] && (
            <>
              {" "}
              Por ejemplo, la casilla de la fila «{stats.durations[0].read_name}» y la columna «
              {stats.durations[0].fix_name}» (
              <span className="homr__num">{fmt(stats.durations[0].n)}</span>) son las veces que HOMR
              leyó «{stats.durations[0].read_name}» donde era «{stats.durations[0].fix_name}».
            </>
          )}
        </p>
        <DurationTable durations={stats.durations} figures={figures} choosing={choosing} />
      </section>

      {history && onChoose && (
        <HistoryPanel history={history} selected={selected} onChoose={onChoose} />
      )}
    </>
  );
  const scoreRow =
    selected?.key.startsWith(SCORE_PREFIX) && history
      ? history.find((row) => `${SCORE_PREFIX}${row.id}` === selected.key)
      : undefined;

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
              <li key={fact.kicker}>
                <Choice
                  className="homr__finding"
                  selection={
                    fact.key
                      ? { key: fact.key, title: fact.title ?? "", kicker: fact.kicker }
                      : null
                  }
                  {...choosing}
                >
                  <span className="label homr__muted">{fact.kicker}</span>
                  <b className="homr__big">{fact.big}</b>
                  <span className="homr__finding-text">
                    <FindingText fact={fact} figures={figures} />
                  </span>
                  {onChoose && fact.key && (
                    <span className="label homr__muted homr__more">Ver ejemplos</span>
                  )}
                </Choice>
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
          {withExamples && (
            <span className="homr__count">Elige una cifra para ver sus ejemplos</span>
          )}
        </div>
        {withExamples ? (
          <div className="homr__layout">
            <div className="homr__charts">{charts}</div>
            {selected && scoreRow ? (
              <ScoreExamples
                key={selected.key}
                group={id}
                row={scoreRow}
                selected={selected}
                corpus={name}
                load={loadScore}
              />
            ) : (
              <ExamplesPanel
                key={selected?.key ?? ""}
                content={figureExamples(id, stats, selected)}
                selected={selected}
                corpus={name}
              />
            )}
          </div>
        ) : (
          <>
            <p className="homr__band-note">
              Los ejemplos con su compás dibujado y el historial de transcripciones solo se enseñan
              de los corpus públicos (PrIMuS y Camera-PrIMuS). De Cadenza salen solo cifras de
              conjunto: nada de una transcripción concreta, como dice el permiso de uso de los
              datos.
            </p>
            {charts}
          </>
        )}
      </section>
    </>
  );
});

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

function OpsBars({
  ops,
  read,
  choosing,
}: {
  ops: Record<string, number>;
  read: number;
  choosing: Choosing;
}) {
  const rows = Object.entries(ops)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (!read || !rows.length) return <p className="homr__panel-note">Sin correcciones.</p>;
  const top = Math.max(...rows.map(([, n]) => n));
  return (
    <ul className="homr__bars" role="list">
      {rows.map(([op, n]) => {
        const per100 = perHundred(n, read);
        const unit = isBarline(op) ? "barras" : "correcciones";
        return (
          <li key={op}>
            <Choice
              className="homr__bar"
              selection={{ key: `op:${op}`, title: opName(op), kicker: "Qué se corrige" }}
              tip={tipProps(opName(op), `${fmt(n)} ${unit}, ${per100} por cada 100 notas`)}
              {...choosing}
            >
              <span className="homr__bar-name">{opName(op)}</span>
              <span className="homr__bar-track" aria-hidden="true">
                <span className="homr__bar-fill" style={{ width: `${String((100 * n) / top)}%` }} />
              </span>
              <span className="homr__bar-value">
                {per100}
                <span className="visually-hidden">
                  {" "}
                  por cada 100 notas ({fmt(n)} {unit})
                </span>
              </span>
            </Choice>
          </li>
        );
      })}
    </ul>
  );
}

const STEPS = Array.from({ length: 17 }, (_, i) => i - 8);

function StepsChart({ steps, choosing }: { steps: Record<string, number>; choosing: Choosing }) {
  const total = Object.values(steps).reduce((a, b) => a + b, 0);
  if (!total) return <p className="homr__panel-note">Sin correcciones de altura.</p>;
  const top = Math.max(1, ...Object.values(steps));
  return (
    <figure className="homr__steps">
      <ol className="homr__steps-cols" role="list">
        {STEPS.map((step) => {
          const n = steps[String(step)] ?? 0;
          if (!n) return <li key={step} className="homr__steps-slot" aria-hidden="true" />;
          return (
            <li key={step} className="homr__steps-slot">
              <Choice
                className="homr__steps-col"
                selection={{
                  key: `step:${String(step)}`,
                  title: `Altura: ${stepName(step)}`,
                  kicker: "Cuánto se movió la altura",
                }}
                tip={tipProps(stepName(step), `${fmt(n)} (${pct(n, total)})`)}
                {...choosing}
              >
                <span
                  className="homr__steps-fill"
                  style={{ height: `${String((100 * n) / top)}%` }}
                  aria-hidden="true"
                />
                <span className="visually-hidden">
                  {stepName(step)}: {fmt(n)} ({pct(n, total)})
                </span>
              </Choice>
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
  choosing,
}: {
  title: string;
  rows: ErrorRateRead[];
  figures?: Record<string, FigureRead>;
  choosing: Choosing;
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
          <li key={row.key}>
            <Choice
              className="homr__bar"
              selection={{ key: row.key, title: row.label, kicker: title }}
              tip={tipProps(row.label, `${fmt(row.wrong)} de ${fmt(row.n)} notas con corrección`)}
              {...choosing}
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
            </Choice>
          </li>
        ))}
      </ul>
      <Pager label={`Páginas de «${title}»`} page={current} pages={pages} onPage={setPage} />
    </div>
  );
}

function DurationTable({
  durations,
  figures,
  choosing,
}: {
  durations: HomrErrorStatsValuesRead["durations"];
  figures: Record<string, FigureRead>;
  choosing: Choosing;
}) {
  if (!durations.length) return <p className="homr__panel-note">Sin correcciones de figura.</p>;
  const matrix = durationMatrix(durations);
  return (
    <div
      className="homr__scroll"
      role="region"
      aria-label="Matriz de la figura leída y correcta"
      tabIndex={0}
    >
      <table className="homr__matrix">
        <thead>
          <tr>
            <td className="homr__corner" colSpan={2} rowSpan={3} />
            <th
              className="homr__axis homr__axis--top"
              colSpan={matrix.fixes.length}
              scope="colgroup"
            >
              La figura que era
            </th>
          </tr>
          <tr>
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
          {matrix.reads.map((readBeats, index) => (
            <tr key={readBeats}>
              {index === 0 && (
                <th
                  className="homr__axis homr__axis--side"
                  rowSpan={matrix.reads.length}
                  scope="rowgroup"
                >
                  <span>La que leyó HOMR</span>
                </th>
              )}
              <th scope="row">
                <FigureSymbol figure={figures[readBeats]} />
                {matrix.names[readBeats]}
              </th>
              {matrix.fixes.map((fix) => {
                const n = matrix.count(readBeats, fix);
                if (!n) return <td key={fix} />;
                const alpha = cellAlpha(n, matrix.max);
                const share = Math.round(alpha * 100);
                const title = `HOMR leyó ${matrix.names[readBeats] ?? ""}, era ${matrix.names[fix] ?? ""}`;
                return (
                  <td
                    key={fix}
                    className={
                      alpha >= STRONG_ALPHA ? "homr__cell homr__cell--strong" : "homr__cell"
                    }
                    style={{
                      backgroundColor: `color-mix(in srgb, var(--color-accent) ${String(share)}%, var(--color-paper))`,
                    }}
                  >
                    <Choice
                      className="homr__cell-value"
                      selection={{
                        key: `dur:${readBeats}>${fix}`,
                        title,
                        kicker: "Figura leída y correcta",
                      }}
                      tip={tipProps(title, fmt(n))}
                      label={`${title}: ${fmt(n)}`}
                      {...choosing}
                    >
                      {fmt(n)}
                    </Choice>
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
