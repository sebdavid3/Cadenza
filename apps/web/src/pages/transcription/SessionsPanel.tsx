import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "../../api/instance";
import { errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import {
  formatDate,
  listSessions,
  listUsers,
  SESSIONS_PAGE_SIZE,
  SESSIONS_QUERY_KEY,
  statusLabel,
} from "./sessions";
import { SessionThumb } from "./SessionThumb";

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

  const rows = sessions.data?.pages.flat() ?? [];

  return (
    <section className="panel sessions" aria-labelledby="sessions-title">
      <div className="panel__head">
        <h2 id="sessions-title" className="panel__title">
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

      {sessions.isError && (
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
        <table className="sessions__table">
          <thead>
            <tr>
              <th scope="col">
                <span className="visually-hidden">Imagen</span>
              </th>
              <th scope="col">Sesión</th>
              <th scope="col">Creada</th>
              <th scope="col">Estado</th>
              <th scope="col" className="num">
                Hallazgos
              </th>
              <th scope="col" className="num">
                Ediciones
              </th>
              {isResearcher && <th scope="col">Propietario</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((session) => (
              <tr key={session.session_id}>
                <td className="sessions__thumb">
                  <SessionThumb sessionId={session.session_id} />
                </td>
                <td>
                  <span className="label sessions__id">{session.session_id.slice(0, 8)}</span>
                </td>
                <td>
                  <time dateTime={session.created_at}>{formatDate(session.created_at)}</time>
                </td>
                <td>
                  <span className="chip chip--status">{statusLabel(session.status)}</span>
                </td>
                <td className="num" data-label="Hallazgos">
                  {session.findings_count ?? 0}
                </td>
                <td className="num" data-label="Ediciones">
                  {session.edits_count ?? 0}
                </td>
                {isResearcher && <td data-label="Propietario">{ownerName(session.owner_id)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {sessions.hasNextPage && (
        <button
          type="button"
          className="button sessions__more"
          disabled={sessions.isFetchingNextPage}
          onClick={() => void sessions.fetchNextPage()}
        >
          {sessions.isFetchingNextPage ? "Cargando…" : "Cargar más"}
        </button>
      )}
      {sessions.isFetchNextPageError && (
        <p className="panel__error" role="alert">
          {errorMessage(sessions.error)}
        </p>
      )}
    </section>
  );
}
