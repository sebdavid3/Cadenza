import { Link } from "react-router";
import { REPOSITORY_URL } from "../config";
import "./button.css";
import "./site-header.css";

/** Cabecera de las páginas públicas: marca, anclas de la landing y acceso. */
export function SiteHeader({
  showSections = true,
  showEnter = true,
}: {
  showSections?: boolean;
  showEnter?: boolean;
}) {
  return (
    <header className="site-header">
      <Link className="site-header__brand" to="/" aria-label="Cadenza, inicio">
        Cadenza
      </Link>
      <span className="label site-header__tagline">Partituras impresas, notación editable</span>
      <nav className="site-header__nav" aria-label="Principal">
        {showSections && (
          <>
            <a className="label" href="#como-funciona">
              Cómo funciona
            </a>
            <a className="label" href="#alcance">
              Alcance
            </a>
          </>
        )}
        <a className="label" href={REPOSITORY_URL}>
          Código
        </a>
      </nav>
      {showEnter && (
        <Link className="button site-header__enter" to="/entrar">
          Entrar
        </Link>
      )}
    </header>
  );
}
