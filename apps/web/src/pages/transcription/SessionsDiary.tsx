import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { api } from "../../api/instance";
import { errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import type { SessionSummaryRead } from "../../types";
import { dayParts, daysWithToday, groupByDay, relativeDay, type Day } from "./days";
import { useQueueStore } from "./queue";
import { QueuePanel } from "./QueuePanel";
import { SessionPlate } from "./SessionPlate";
import { listSessions, listUsers, SESSIONS_PAGE_SIZE, SESSIONS_QUERY_KEY } from "./sessions";

/**
 * La paginación es por offset: si se crea una sesión entre dos páginas, la última de una vuelve
 * a salir al principio de la siguiente. Cada sesión se pinta una sola vez.
 */
function uniqueSessions(pages: SessionSummaryRead[][]): SessionSummaryRead[] {
  const seen = new Set<string>();
  return pages.flat().filter((session) => {
    if (seen.has(session.session_id)) return false;
    seen.add(session.session_id);
    return true;
  });
}

interface DayBandProps {
  day: Day;
  now: Date;
  /** La cola, en el día de hoy y solo mientras hay imágenes. */
  queue: ReactNode;
  owner: (session: SessionSummaryRead) => string | null;
}

/** Un día del diario: la fecha en el margen y sus láminas, la más reciente primero. */
function DayBand({ day, now, queue, owner }: DayBandProps) {
  const parts = dayParts(day);
  const relative = relativeDay(day, now);
  const headingId = `day-${day.key}`;
  return (
    <section className="day" aria-labelledby={headingId} data-today={relative === "Hoy"}>
      <div className="day__margin">
        <h2 className="day__date" id={headingId}>
          <span className="visually-hidden">
            {relative ? `${relative}, ` : ""}
            {parts.full}
          </span>
          <span className="day__number" aria-hidden="true">
            {parts.number}
          </span>
          <span className="label day__month" aria-hidden="true">
            {parts.monthYear}
          </span>
          {relative && (
            <span className="label day__relative" aria-hidden="true">
              {relative}
            </span>
          )}
        </h2>
      </div>
      <div className="day__body">
        {queue}
        {day.sessions.length > 0 && (
          // role="list": sin viñetas, Safari y VoiceOver dejan de tratarla como lista.
          <ol className="plates" role="list">
            {day.sessions.map((session) => (
              <SessionPlate key={session.session_id} session={session} owner={owner(session)} />
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

/**
 * Las sesiones como diario de trabajo (#370): agrupadas por el día en que se crearon, con la cola
 * dentro de hoy. Sustituye a la tabla y a la columna de la cola.
 */
export function SessionsDiary() {
  const user = useAuthStore((state) => state.user);
  const isResearcher = user?.role === "investigador";
  const queued = useQueueStore((state) => state.items.length > 0);

  const sessions = useInfiniteQuery({
    queryKey: SESSIONS_QUERY_KEY,
    queryFn: ({ pageParam, signal }) => listSessions(api, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, _pages, lastOffset) =>
      lastPage.length === SESSIONS_PAGE_SIZE ? lastOffset + SESSIONS_PAGE_SIZE : undefined,
  });

  // Solo un investigador ve sesiones ajenas; sus nombres salen de GET /users.
  const users = useQuery({
    queryKey: ["users"],
    queryFn: ({ signal }) => listUsers(api, signal),
    enabled: isResearcher,
    staleTime: 5 * 60_000,
  });
  const owner = (session: SessionSummaryRead): string | null => {
    if (!isResearcher) return null;
    const ownerId = session.owner_id;
    if (!ownerId) return "—";
    if (ownerId === user.id) return "Tú";
    return (
      users.data?.find((candidate) => candidate.id === ownerId)?.username ?? ownerId.slice(0, 8)
    );
  };

  const pages = sessions.data?.pages;
  const rows = useMemo(() => uniqueSessions(pages ?? []), [pages]);
  const listed = useMemo(() => new Set(rows.map((row) => row.session_id)), [rows]);
  const now = new Date();
  const days = daysWithToday(groupByDay(rows), now, queued);

  // «Cargar más» no se ofrece mientras el listado pide algo: pedir otra página cancelaría la
  // actualización en curso (y al revés), y la sesión recién creada podría no aparecer.
  const busy = sessions.fetchStatus !== "idle";

  // Tras cargar otra página, el foco pasa a la primera sesión nueva (el botón puede desaparecer),
  // salvo que la persona ya lo haya llevado a otro sitio mientras tanto.
  const diaryRef = useRef<HTMLElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);
  const focusRowAfterLoad = useRef<number | null>(null);
  useEffect(() => {
    const index = focusRowAfterLoad.current;
    if (index === null || sessions.isFetchingNextPage) return;
    focusRowAfterLoad.current = null;
    const active = document.activeElement;
    const waiting = !active || active === document.body || active === moreRef.current;
    if (!waiting) return;
    const first = rows[index]?.session_id;
    const plates = diaryRef.current?.querySelectorAll<HTMLElement>("[data-session-id]") ?? [];
    const plate = [...plates].find((candidate) => candidate.dataset.sessionId === first);
    if (plate) plate.focus();
    else if (!moreRef.current) document.getElementById("transcription-title")?.focus();
  });

  return (
    <section className="diary" aria-label="Sesiones" ref={diaryRef}>
      {days.map((day) => (
        <DayBand
          key={day.key}
          day={day}
          now={now}
          owner={owner}
          queue={queued && relativeDay(day, now) === "Hoy" ? <QueuePanel listed={listed} /> : null}
        />
      ))}

      {sessions.isPending && (
        <p className="diary__note" role="status">
          Cargando sesiones…
        </p>
      )}

      {/* Sin sesiones que enseñar, el error ocupa el sitio del diario. */}
      {sessions.isError && rows.length === 0 && (
        <div className="diary__note">
          <div className="panel__error" role="alert">
            <p>{errorMessage(sessions.error)}</p>
            <button type="button" className="link-button" onClick={() => void sessions.refetch()}>
              Reintentar
            </button>
          </div>
        </div>
      )}

      {sessions.isSuccess && rows.length === 0 && !queued && (
        <div className="diary__empty">
          <p className="diary__empty-title">Todavía no hay sesiones.</p>
          <p>
            Elige las imágenes de tus partituras con «Nueva transcripción» o suéltalas en cualquier
            parte de esta página. Se transcriben de una en una y cada una crea una sesión, que
            aparecerá aquí, en el día en que la hiciste, con los compases que el validador señala.
          </p>
        </div>
      )}

      {((sessions.isError && rows.length > 0) || sessions.hasNextPage) && (
        <div className="diary__foot">
          {/* Con sesiones a la vista, el error de una página más o de una actualización. */}
          {sessions.isError && rows.length > 0 && (
            <div className="panel__error" role="alert">
              <p>
                {sessions.isFetchNextPageError
                  ? "No se pudieron cargar más sesiones."
                  : "No se pudo actualizar el listado."}{" "}
                {errorMessage(sessions.error)}
              </p>
              {!sessions.isFetchNextPageError && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => void sessions.refetch()}
                >
                  Reintentar
                </button>
              )}
            </div>
          )}
          {sessions.hasNextPage && (
            // aria-disabled y no disabled: el botón conserva el foco mientras espera.
            <button
              ref={moreRef}
              type="button"
              className="button diary__more"
              aria-disabled={busy}
              onClick={() => {
                if (busy) return;
                focusRowAfterLoad.current = rows.length;
                void sessions.fetchNextPage();
              }}
            >
              {sessions.isFetchingNextPage ? "Cargando…" : "Cargar más"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
