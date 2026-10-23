import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Outlet } from "react-router";
import { useAuthStore } from "./auth/store";
import { useSessionLifecycle } from "./auth/useSessionLifecycle";

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

  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  );
}
