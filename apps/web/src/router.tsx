import { createBrowserRouter, type RouteObject } from "react-router";
import { AppRoot } from "./AppRoot";
import { RequireAuth } from "./auth/RequireAuth";
import { AppLayout } from "./components/AppLayout";
import { LandingPage } from "./pages/landing/LandingPage";
import { LoginPage } from "./pages/login/LoginPage";
import { NotFoundPage } from "./pages/not-found/NotFoundPage";
import { SessionPage } from "./pages/session/SessionPage";
import { TranscriptionPage } from "./pages/transcription/TranscriptionPage";

// Rutas de la interfaz. Ninguna empieza por /api, el prefijo que el proxy reenvía a la API.
export const routes: RouteObject[] = [
  {
    element: <AppRoot />,
    children: [
      { path: "/", element: <LandingPage /> },
      { path: "/entrar", element: <LoginPage /> },
      {
        element: (
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        ),
        children: [
          { path: "/transcripcion", element: <TranscriptionPage /> },
          { path: "/sesiones/:sessionId", element: <SessionPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
