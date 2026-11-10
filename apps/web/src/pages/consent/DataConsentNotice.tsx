import { Link } from "react-router";
import { DATA_USE_PATH, STORED_DATA } from "./consent";

/**
 * El aviso breve del permiso de uso de los datos (#378, ADR-0065): qué se guarda, para qué y con
 * qué nombre, con el enlace al texto completo. Lo comparten el registro y «Tu cuenta», así que
 * dicen lo mismo. Lo aprobó el responsable del proyecto el 2026-11-09.
 *
 * Desde el registro, el texto completo se abre en otra pestaña (`newTab`): una navegación interna
 * desmontaría el formulario y se perdería lo escrito.
 */
export function DataConsentNotice({ id, newTab = false }: { id?: string; newTab?: boolean }) {
  return (
    <div className="consent-notice" id={id}>
      <p>
        Cadenza forma parte de una investigación. Al usarlo se guardan, con tu nombre de usuario
        (puede ser un seudónimo) y sin tu correo, {STORED_DATA.slice(0, -1).join(", ")} y{" "}
        {STORED_DATA.at(-1)}. Con tu permiso, se podrán usar para investigar y para mejorar el
        modelo que transcribe y el que sugiere correcciones. Puedes retirarlo cuando quieras desde
        «Tu cuenta».
      </p>
      <p>
        {newTab ? (
          <a href={DATA_USE_PATH} target="_blank" rel="noopener">
            Leer el texto completo (se abre en otra pestaña)
          </a>
        ) : (
          <Link to={DATA_USE_PATH}>Leer el texto completo</Link>
        )}
      </p>
    </div>
  );
}
