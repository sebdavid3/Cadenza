import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { api } from "../../api/instance";
import { errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import { PixelIcon } from "../../components/PixelIcon";
import type { SessionSummaryRead } from "../../types";
import {
  formatDay,
  formatTime,
  isoUtc,
  listSessions,
  listUsers,
  SESSIONS_PAGE_SIZE,
  SESSIONS_QUERY_KEY,
  statusLabel,
} from "./sessions";
import { SessionThumb } from "./SessionThumb";

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

export function SessionsPanel() {
  const user = useAuthStore((state) => state.user);
  const isResearcher = user?.role === "investigador";

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
  const ownerName = (ownerId: string | null | undefined) => {
    if (!ownerId) return "—";
    if (ownerId === user?.id) return "Tú";
    return (
      users.data?.find((candidate) => candidate.id === ownerId)?.username ?? ownerId.slice(0, 8)
    );
  };

  const rows = uniqueSessions(sessions.data?.pages ?? []);

  // «Cargar más» no se ofrece mientras el listado pide algo: pedir otra página cancelaría la
  // actualización en curso (y al revés), y la sesión recién creada podría no aparecer.
  const busy = sessions.fetchStatus !== "idle";

  // Tras cargar otra página, el foco pasa a la primera sesión nueva (el botón puede desaparecer),
  // salvo que la persona ya lo haya llevado a otro sitio mientras tanto.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);
  const focusRowAfterLoad = useRef<number | null>(null);
  useEffect(() => {
    const index = focusRowAfterLoad.current;
    if (index === null || sessions.isFetchingNextPage) return;
    focusRowAfterLoad.current = null;
    const active = document.activeElement;
    const waiting = !active || active === document.body || active === moreRef.current;
    if (!waiting) return;
    const row = bodyRef.current?.rows[index];
    if (row) row.focus();
    else if (!moreRef.current) headingRef.current?.focus();
  });

  return (
    <section
      className={isResearcher ? "panel sessions sessions--owner" : "panel sessions"}
      aria-labelledby="sessions-title"
    >
      <div className="panel__head">
        <h2 id="sessions-title" className="panel__title" ref={headingRef} tabIndex={-1}>
          Sesiones
        </h2>
        <p className="label panel__count">
          {isResearcher ? "Todas las sesiones" : "Tus sesiones"} · la más reciente primero
        </p>
      </div>

      {sessions.isPending && (
        <p className="panel__empty" role="status">
          Cargando sesiones…
        </p>
      )}

      {/* Sin filas que enseñar, el error ocupa el sitio del listado. */}
      {sessions.isError && rows.length === 0 && (
        <div className="panel__error" role="alert">
          <p>{errorMessage(sessions.error)}</p>
          <button type="button" className="link-button" onClick={() => void sessions.refetch()}>
            Reintentar
          </button>
        </div>
      )}

      {sessions.isSuccess && rows.length === 0 && (
        <p className="panel__empty">
          Todavía no hay sesiones. Sube una imagen y aquí aparecerá la sesión que crea.
        </p>
      )}

      {rows.length > 0 && (
        <div className="sessions__frame">
          {/* Roles explícitos: en fichas la tabla deja de mostrarse como tabla y los perdería. */}
          <table className="sessions__table" role="table">
            <thead role="rowgroup">
              <tr role="row">
                <th scope="col" role="columnheader">
                  <span className="visually-hidden">Imagen</span>
                </th>
                <th scope="col" role="columnheader">
                  Sesión
                </th>
                <th scope="col" role="columnheader">
                  Creada
                </th>
                <th scope="col" role="columnheader">
                  Estado
                </th>
                <th scope="col" role="columnheader" className="num">
                  Hallazgos
                </th>
                <th scope="col" role="columnheader" className="num">
                  Ediciones
                </th>
                {isResearcher && (
                  <th scope="col" role="columnheader">
                    Propietario
                  </th>
                )}
              </tr>
            </thead>
            <tbody role="rowgroup" ref={bodyRef}>
              {rows.map((session) => (
                <tr key={session.session_id} role="row" tabIndex={-1}>
                  <td role="cell" className="sessions__thumb">
                    <SessionThumb sessionId={session.session_id} />
                  </td>
                  <td role="cell" className="sessions__key">
                    <Link
                      className="label sessions__id"
                      to={`/sesiones/${encodeURIComponent(session.session_id)}`}
                      aria-label={`Ver la sesión ${session.session_id.slice(0, 8)}`}
                    >
                      {session.session_id.slice(0, 8)}
                      <PixelIcon name="arrow-right" />
                    </Link>
                  </td>
                  <td role="cell" className="sessions__date">
                    <time dateTime={isoUtc(session.created_at)}>
                      <span>{formatDay(session.created_at)}</span>{" "}
                      <span>{formatTime(session.created_at)}</span>
                    </time>
                  </td>
                  <td role="cell" className="sessions__status">
                    <span className="chip chip--status">{statusLabel(session.status)}</span>
                  </td>
                  <td role="cell" className="num sessions__findings" data-label="Hallazgos">
                    {(session.findings_count ?? 0) > 0 ? (
                      <span className="chip chip--finding">{session.findings_count}</span>
                    ) : (
                      0
                    )}
                  </td>
                  <td role="cell" className="num sessions__edits" data-label="Ediciones">
                    {session.edits_count ?? 0}
                  </td>
                  {isResearcher && (
                    <td role="cell" className="sessions__owner" data-label="Propietario">
                      {ownerName(session.owner_id)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Con filas a la vista, el error de una página más o de una actualización va debajo. */}
      {sessions.isError && rows.length > 0 && (
        <div className="panel__error" role="alert">
          <p>
            {sessions.isFetchNextPageError
              ? "No se pudieron cargar más sesiones."
              : "No se pudo actualizar el listado."}{" "}
            {errorMessage(sessions.error)}
          </p>
          {!sessions.isFetchNextPageError && (
            <button type="button" className="link-button" onClick={() => void sessions.refetch()}>
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
          className="button sessions__more"
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
    </section>
  );
}
