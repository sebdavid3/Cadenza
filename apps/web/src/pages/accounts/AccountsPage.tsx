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
 * Por fecha de alta, la más reciente arriba. Activar o desactivar no cambia la fecha, así que la
 * fila que tiene el foco no salta de sitio.
 */
function byNewest(users: readonly UserRead[]): UserRead[] {
  return [...users].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
}

/**
 * Gestión mínima de cuentas para investigadores (ADR-0022, ADR-0025): ver quién se registró y
 * desactivar una cuenta que se use mal, o volver a activarla. Las del registro entran en el
 * momento y se distinguen de las del estudio. Para un transcriptor la ruta no existe (la API le
 * respondería 403 de todos modos).
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
  const rows = byNewest(users.data ?? []);
  const fromRegistration = rows.filter((user) => user.self_registered === true).length;
  // Un cambio cada vez: el resultado de cada uno se ve y se anuncia.
  const busy = toggle.isPending;

  return (
    <main className="accounts">
      <header className="accounts__head">
        <h1 className="accounts__title">Cuentas</h1>
        <p className="accounts__lead">
          Cualquiera puede crear una cuenta desde el registro y entra en el momento. Esas cuentas no
          forman parte del estudio; las del estudio las crea un investigador. Desactiva una cuenta
          para que no pueda entrar, por ejemplo si se usa mal.
        </p>
      </header>

      <section className="accounts__panel" aria-labelledby="accounts-list-title">
        <div className="accounts__bar">
          <h2 id="accounts-list-title" className="accounts__subtitle">
            Todas las cuentas
          </h2>
          {users.isSuccess && (
            <p className="label accounts__count">
              {`${String(rows.length)} ${rows.length === 1 ? "cuenta" : "cuentas"}, ${String(fromRegistration)} del registro`}
            </p>
          )}
          <button
            type="button"
            className="link-button"
            aria-disabled={users.isFetching}
            onClick={() => {
              if (users.isFetching) return;
              void users.refetch();
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
              const state = user.active ? "active" : "inactive";
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
                    {user.active ? "Activa" : "Desactivada"}
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
