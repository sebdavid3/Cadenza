import { createBrowserRouter, type RouteObject } from "react-router";
import { LandingPage } from "./pages/landing/LandingPage";
import { NotFoundPage } from "./pages/not-found/NotFoundPage";

// Rutas de la interfaz. Ninguna empieza por /api, el prefijo que el proxy reenvía a la API.
export const routes: RouteObject[] = [
  { path: "/", element: <LandingPage /> },
  { path: "*", element: <NotFoundPage /> },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
