import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/instance";
import { errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { NotFoundPage } from "../not-found/NotFoundPage";
import type { UserRead } from "../../types";
import { formatDay, listUsers } from "../transcription/sessions";
import "./accounts.css";

const USERS_QUERY_KEY = ["users"] as const;

const ROLE_LABELS: Record<string, string> = {
  investigador: "Investigador",
  transcriptor: "Transcriptor",
};

function setActive(userId: string, active: boolean) {
  return api.request<UserRead>(`/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    json: { active },
  });
}

/** Pendientes de activar primero; después, por fecha de alta, la más reciente arriba. */
function sortAccounts(users: readonly UserRead[]) {
  const pending = (user: UserRead) => !user.active && user.self_registered === true;
  return [...users].sort((a, b) => {
    if (pending(a) !== pending(b)) return pending(a) ? -1 : 1;
    return (b.created_at ?? "").localeCompare(a.created_at ?? "");
  });
}

/**
 * Gestión mínima de cuentas para investigadores (ADR-0022): ver quién se registró y activar o
 * desactivar cuentas. Las autorregistradas se distinguen de las del estudio. Para un
 * transcriptor la ruta no existe (la API le respondería 403 de todos modos).
 */
export function AccountsPage() {
  const role = useAuthStore((state) => state.user?.role);
  if (role !== "investigador") return <NotFoundPage />;
  return <AccountsView />;
}

function AccountsView() {
  useDocumentTitle("Cuentas");
  const me = useAuthStore((state) => state.user);
  const queryClient = useQueryClient();
  const users = useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: ({ signal }) => listUsers(api, signal),
  });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => setActive(id, active),
    onSuccess: (updated) => {
      queryClient.setQueryData<UserRead[]>(USERS_QUERY_KEY, (previous) =>
        previous?.map((user) => (user.id === updated.id ? updated : user)),
      );
    },
  });

  const rows = sortAccounts(users.data ?? []);
  const pendingCount = rows.filter((user) => !user.active && user.self_registered).length;

  return (
    <main className="accounts">
      <header className="accounts__head">
        <h1 className="accounts__title">Cuentas</h1>
        <p className="accounts__lead">
          Las cuentas creadas desde el registro nacen inactivas: actívalas para que puedan entrar y
          transcribir. No forman parte del estudio; las del estudio las crea un investigador.
        </p>
      </header>

      <section className="accounts__panel" aria-labelledby="accounts-list-title">
        <div className="accounts__bar">
          <h2 id="accounts-list-title" className="accounts__subtitle">
            Todas las cuentas
          </h2>
          {users.isSuccess && (
            <p className="label accounts__count">
              {pendingCount === 0
                ? "Ninguna pendiente"
                : `${String(pendingCount)} pendiente${pendingCount === 1 ? "" : "s"} de activar`}
            </p>
          )}
        </div>

        {users.isPending && (
          <p className="accounts__empty" role="status">
            Cargando cuentas…
          </p>
        )}
        {users.isError && (
          <div className="accounts__error" role="alert">
            <p>{errorMessage(users.error)}</p>
            <button type="button" className="link-button" onClick={() => void users.refetch()}>
              Reintentar
            </button>
          </div>
        )}
        {toggle.isError && (
          <p className="accounts__error" role="alert">
            No se pudo cambiar la cuenta. {errorMessage(toggle.error)}
          </p>
        )}

        {rows.length > 0 && (
          <ul className="accounts__list" role="list">
            {rows.map((user) => {
              const own = user.id === me?.id;
              const busy = toggle.isPending && toggle.variables.id === user.id;
              const state = user.active ? "active" : user.self_registered ? "pending" : "inactive";
              return (
                <li key={user.id} className="accounts__item" data-state={state}>
                  <div className="accounts__who">
                    <span className="accounts__name">{user.username}</span>
                    <span className="label accounts__meta">
                      {ROLE_LABELS[user.role] ?? user.role} ·{" "}
                      {user.self_registered ? "Registro" : "Creada por un investigador"}
                      {user.created_at ? ` · ${formatDay(user.created_at)}` : ""}
                    </span>
                  </div>
                  <span className="label accounts__state">
                    {state === "active" ? "Activa" : state === "pending" ? "Pendiente" : "Inactiva"}
                  </span>
                  {own ? (
                    <span className="label accounts__own">Tu cuenta</span>
                  ) : (
                    <button
                      type="button"
                      className="button"
                      aria-disabled={busy}
                      aria-label={`${user.active ? "Desactivar" : "Activar"} la cuenta ${user.username}`}
                      onClick={() => {
                        if (busy) return;
                        toggle.mutate({ id: user.id, active: !user.active });
                      }}
                    >
                      {busy ? "Guardando…" : user.active ? "Desactivar" : "Activar"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}
