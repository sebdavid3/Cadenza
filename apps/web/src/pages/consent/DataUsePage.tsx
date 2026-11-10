import { Link } from "react-router";
import { useAuthStore } from "../../auth/store";
import { SiteHeader } from "../../components/SiteHeader";
import { registrationEnabled } from "../../config";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { consentVersionLabel } from "./consent";
import { DataUseText } from "./DataUseText";
import "./consent.css";

/**
 * La página con el texto completo del permiso de uso de los datos (#378, ADR-0065). Es pública: se
 * puede leer antes de crear la cuenta. El texto vive en `DataUseText`, que también se despliega en
 * el registro (#397); la página lo compone en bandas, con el título de cada apartado a la izquierda.
 */
export function DataUsePage() {
  useDocumentTitle("Uso de tus datos");
  const authenticated = useAuthStore((state) => state.status === "authenticated");
  return (
    <>
      <SiteHeader showSections={false} />
      <main className="data-use" aria-labelledby="data-use-title">
        <div className="data-use__head">
          <h1 id="data-use-title" className="data-use__title">
            Uso de tus datos
          </h1>
          <p className="label data-use__version">Versión del {consentVersionLabel()}</p>
        </div>

        <DataUseText layout="page" />

        <p className="data-use__back">
          {authenticated ? (
            <Link to="/cuenta">Ir a «Tu cuenta»</Link>
          ) : registrationEnabled() ? (
            <Link to="/registro">Volver a crear una cuenta</Link>
          ) : (
            <Link to="/">Volver a la portada</Link>
          )}
        </p>
      </main>
    </>
  );
}
