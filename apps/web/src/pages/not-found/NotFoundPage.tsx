import { Link } from "react-router";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "./not-found.css";

export function NotFoundPage() {
  useDocumentTitle("Página no encontrada");

  return (
    <main className="not-found">
      <p className="not-found__code" aria-hidden="true">
        404
      </p>
      <h1 className="not-found__title">Esta página no existe.</h1>
      <p className="not-found__text">
        Puede que el enlace esté mal escrito o que la página se haya movido.
      </p>
      <Link className="button" to="/">
        <PixelIcon name="arrow-left" />
        Volver al inicio
      </Link>
    </main>
  );
}
