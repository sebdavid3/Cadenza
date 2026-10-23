import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Outlet } from "react-router";
import { useAuthStore } from "./auth/store";
import { useSessionLifecycle } from "./auth/useSessionLifecycle";
import { pendingWorkWarning } from "./pendingWork";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 },
    },
  });
}

/** Raíz de todas las rutas: mantiene la sesión del navegador y la caché de datos del servidor. */
export function AppRoot() {
  useSessionLifecycle();
  const [queryClient] = useState(createQueryClient);
  const token = useAuthStore((state) => state.token);

  // Lo que una persona vio no debe quedar en caché para la siguiente sesión de la pestaña.
  useEffect(() => {
    if (!token) queryClient.clear();
  }, [token, queryClient]);

  // Cerrar o recargar la pestaña con trabajo pendiente lo perdería: el navegador pide
  // confirmación, también fuera de la vista que lo creó.
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!pendingWorkWarning()) return;
      event.preventDefault();
      // Chrome anterior a la 119 solo pregunta si además se asigna returnValue (MDN).
      // eslint-disable-next-line @typescript-eslint/no-deprecated -- compatibilidad, ver arriba
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  );
}
