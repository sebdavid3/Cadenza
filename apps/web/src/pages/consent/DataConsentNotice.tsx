import { Link } from "react-router";
import { DATA_USE_PATH, STORED_DATA } from "./consent";

/**
 * El aviso breve del permiso de uso de los datos (#378, ADR-0064): qué se guarda, para qué y con
 * seudónimo, con el enlace al texto completo. Lo comparten el registro y «Tu cuenta», así que
 * dicen lo mismo. Es una propuesta que aprueba el responsable del proyecto.
 */
export function DataConsentNotice({ id }: { id?: string }) {
  return (
    <div className="consent-notice" id={id}>
      <p>
        Cadenza forma parte de una investigación. Al usarlo se guardan, con tu seudónimo y sin tu
        nombre ni tu correo, {STORED_DATA.slice(0, -1).join(", ")} y {STORED_DATA.at(-1)}. Con tu
        permiso, se podrán usar para investigar y para mejorar el modelo que transcribe y el que
        sugiere correcciones. Puedes retirarlo cuando quieras desde «Tu cuenta».
      </p>
      <p>
        <Link to={DATA_USE_PATH}>Leer el texto completo</Link>
      </p>
    </div>
  );
}
