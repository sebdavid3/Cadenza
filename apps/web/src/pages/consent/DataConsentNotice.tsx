import { useId, useState } from "react";
import { Link } from "react-router";
import { consentVersionLabel, DATA_USE_PATH, STORED_DATA } from "./consent";
import { DataUseText } from "./DataUseText";

/**
 * El aviso breve del permiso de uso de los datos (#378, ADR-0065): qué se guarda, para qué y con
 * qué nombre, con el texto completo. Lo comparten el registro y «Tu cuenta», así que dicen lo
 * mismo. Lo aprobó el responsable del proyecto el 2026-11-09.
 *
 * Desde el registro (`expandable`), el texto completo se despliega bajo el aviso, en un recuadro
 * con su propio desplazamiento (#397): ni otra pestaña ni una navegación, que desmontaría el
 * formulario y se perdería lo escrito. El `id` va en el párrafo del aviso, y el texto desplegado
 * fuera de él, porque la casilla se describe con el aviso y la descripción debe seguir siendo
 * breve. Desde «Tu cuenta», enlaza a la página.
 */
export function DataConsentNotice({
  id,
  expandable = false,
}: {
  id?: string;
  expandable?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const fullId = useId();
  return (
    <>
      <div className="consent-notice">
        <p id={id}>
          Cadenza forma parte de una investigación. Al usarlo se guardan, con tu nombre de usuario
          (puede ser un seudónimo) y sin tu correo, {STORED_DATA.slice(0, -1).join(", ")} y{" "}
          {STORED_DATA.at(-1)}. Con tu permiso, se podrán usar para investigar y para mejorar el
          modelo que transcribe y el que sugiere correcciones. Puedes retirarlo cuando quieras desde
          «Tu cuenta».
        </p>
        <p>
          {expandable ? (
            <button
              type="button"
              className="consent-toggle"
              aria-expanded={open}
              aria-controls={fullId}
              onClick={() => {
                setOpen((value) => !value);
              }}
            >
              {open ? "Ocultar el texto completo" : "Leer el texto completo"}
            </button>
          ) : (
            <Link to={DATA_USE_PATH}>Leer el texto completo</Link>
          )}
        </p>
      </div>
      {expandable && (
        // Con su propio desplazamiento: se enfoca para recorrerlo con el teclado.
        <div
          id={fullId}
          className="consent-full"
          role="region"
          aria-label="Texto completo del permiso"
          tabIndex={0}
          hidden={!open}
        >
          <p className="label consent-full__version">Versión del {consentVersionLabel()}</p>
          <DataUseText layout="inline" />
        </div>
      )}
    </>
  );
}
