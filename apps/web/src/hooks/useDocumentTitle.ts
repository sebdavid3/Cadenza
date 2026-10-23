import { useEffect } from "react";

const APP_NAME = "Cadenza";

/** Fija el título de la pestaña: «<página> · Cadenza», o solo «Cadenza». */
export function useDocumentTitle(page?: string) {
  useEffect(() => {
    document.title = page ? `${page} · ${APP_NAME}` : APP_NAME;
  }, [page]);
}
