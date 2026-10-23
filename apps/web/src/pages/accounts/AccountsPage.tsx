import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/instance";
import { errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { UserRead } from "../../types";
import { NotFoundPage } from "../not-found/NotFoundPage";
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

/**
 * Del registro y sin activar: espera una decisión del investigador. Desactivar una cuenta
 * autorregistrada la deja igual (la API no distingue «rechazada»), y por eso no se llama
 * «pendiente».
 */
const awaitsDecision = (user: UserRead) => !user.active && user.self_registered === true;

/** Sin activar primero; después, por fecha de alta, la más reciente arriba. */
function sortedIds(users: readonly UserRead[]): string[] {
  return [...users]
    .sort((a, b) => {
      if (awaitsDecision(a) !== awaitsDecision(b)) return awaitsDecision(a) ? -1 : 1;
      return (b.created_at ?? "").localeCompare(a.created_at ?? "");
    })
    .map((user) => user.id);
}

/**
 * El orden se fija al cargar (o al actualizar a mano) y no cambia al activar una cuenta: la fila
 * que tiene el foco no salta de sitio. Las cuentas que no estaban se añaden al final.
 */
function useStableOrder(users: readonly UserRead[] | undefined) {
  const [order, setOrder] = useState<string[]>([]);
  const [source, setSource] = useState<readonly UserRead[] | undefined>(undefined);
  if (users !== source) {
    setSource(users);
    const known = new Set(order);
    const ids = users ? sortedIds(users) : [];
    setOrder(
      order.length === 0
        ? ids
        : [...order.filter((id) => ids.includes(id)), ...ids.filter((id) => !known.has(id))],
    );
  }
  const byId = new Map((users ?? []).map((user) => [user.id, user]));
  return {
    rows: order.flatMap((id) => byId.get(id) ?? []),
    resort: () => {
      setOrder(users ? sortedIds(users) : []);
    },
  };
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
  const [announcement, setAnnouncement] = useState("");
  const toggle = useMutation({
    mutationFn: ({ user, active }: { user: UserRead; active: boolean }) =>
      setActive(user.id, active),
    // Una recarga en curso no debe pisar el resultado del cambio.
    onMutate: () => queryClient.cancelQueries({ queryKey: USERS_QUERY_KEY }),
    onSuccess: (updated) => {
      queryClient.setQueryData<UserRead[]>(USERS_QUERY_KEY, (previous) =>
        previous?.map((user) => (user.id === updated.id ? updated : user)),
      );
      setAnnouncement(`Cuenta ${updated.username} ${updated.active ? "activada" : "desactivada"}.`);
    },
  });
  const { rows, resort } = useStableOrder(users.data);
  const waiting = rows.filter(awaitsDecision).length;
  // Un cambio cada vez: el resultado de cada uno se ve y se anuncia.
  const busy = toggle.isPending;

  return (
    <main className="accounts">
      <header className="accounts__head">
        <h1 className="accounts__title">Cuentas</h1>
        <p className="accounts__lead">
          Las cuentas creadas desde el registro nacen sin activar: actívalas para que puedan entrar
          y transcribir. No forman parte del estudio; las del estudio las crea un investigador. Una
          cuenta del registro que desactives vuelve a contar como sin activar, también para el
          límite de cuentas en espera del registro.
        </p>
      </header>

      <section className="accounts__panel" aria-labelledby="accounts-list-title">
        <div className="accounts__bar">
          <h2 id="accounts-list-title" className="accounts__subtitle">
            Todas las cuentas
          </h2>
          {users.isSuccess && (
            <p className="label accounts__count">
              {waiting === 0
                ? "Ninguna del registro sin activar"
                : `${String(waiting)} del registro sin activar`}
            </p>
          )}
          <button
            type="button"
            className="link-button"
            aria-disabled={users.isFetching}
            onClick={() => {
              if (users.isFetching) return;
              void users.refetch().then(() => {
                resort();
              });
            }}
          >
            {users.isFetching && users.isSuccess ? "Actualizando…" : "Actualizar"}
          </button>
        </div>

        <p className="visually-hidden" role="status">
          {announcement}
        </p>

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
            No se pudo cambiar la cuenta {toggle.variables.user.username}.{" "}
            {errorMessage(toggle.error)}
          </p>
        )}

        {rows.length > 0 && (
          <ul className="accounts__list" role="list">
            {rows.map((user) => {
              const own = user.id === me?.id;
              const saving = busy && toggle.variables.user.id === user.id;
              const state = user.active ? "active" : awaitsDecision(user) ? "waiting" : "inactive";
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
                    {state === "active" ? "Activa" : "Sin activar"}
                  </span>
                  {own ? (
                    <span className="label accounts__own">Tu cuenta</span>
                  ) : (
                    <button
                      type="button"
                      className="button"
                      aria-disabled={busy}
                      aria-label={
                        saving
                          ? undefined
                          : `${user.active ? "Desactivar" : "Activar"} la cuenta ${user.username}`
                      }
                      onClick={() => {
                        if (busy) return;
                        setAnnouncement("");
                        toggle.mutate({ user, active: !user.active });
                      }}
                    >
                      {saving ? "Guardando…" : user.active ? "Desactivar" : "Activar"}
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
