import { Link } from "react-router";
import { useAuthStore } from "../../auth/store";
import { SiteHeader } from "../../components/SiteHeader";
import { registrationEnabled } from "../../config";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { consentVersionLabel, STORED_DATA } from "./consent";
import "./consent.css";

/**
 * El texto completo del permiso de uso de los datos (#378, ADR-0064), versión del 9 de noviembre
 * de 2026. Es público: se puede leer antes de crear la cuenta. Es una propuesta que aprueba el
 * responsable del proyecto; si cambia, cambia también `DATA_CONSENT_VERSION`.
 */
export function DataUsePage() {
  useDocumentTitle("Uso de tus datos");
  const authenticated = useAuthStore((state) => state.status === "authenticated");
  return (
    <>
      <SiteHeader showSections={false} />
      <main className="data-use" aria-labelledby="data-use-title">
        <h1 id="data-use-title" className="data-use__title">
          Uso de tus datos
        </h1>
        <p className="label data-use__version">Versión del {consentVersionLabel()}</p>

        <section aria-labelledby="data-use-what">
          <h2 id="data-use-what">Qué se guarda</h2>
          <p>Cuando usas Cadenza con tu cuenta, se guarda:</p>
          <ul>
            {STORED_DATA.map((item) => (
              <li key={item}>{item.charAt(0).toUpperCase() + item.slice(1)}.</li>
            ))}
            <li>
              Los datos que das de cada partitura (título, compositor e instrumentos) y los posibles
              errores que descartas o restauras.
            </li>
          </ul>
          <p>
            Todo va unido a tu cuenta, que se identifica por su nombre de usuario: no te pedimos tu
            nombre ni tu correo, y el usuario puede ser un seudónimo. Hace falta guardarlo para que
            puedas volver a tus transcripciones; el permiso decide si, además, se puede usar para lo
            que sigue. Como cualquier web, el servidor guarda además un registro técnico de las
            peticiones, con su dirección IP, que solo sirve para que funcione y se va borrando.
          </p>
        </section>

        <section aria-labelledby="data-use-why">
          <h2 id="data-use-why">Para qué, con tu permiso</h2>
          <ul>
            <li>
              Para investigar: Cadenza es parte de una tesis sobre cuánto cuesta corregir una
              partitura que ha leído una máquina, y sobre cómo ayudar a hacerlo.
            </li>
            <li>
              Para mejorar el modelo que transcribe las partituras y el que sugiere correcciones,
              aprendiendo de los errores que corriges.
            </li>
          </ul>
          <p>
            Lo que se publique de la investigación irá en cifras de conjunto, nunca con tu nombre de
            usuario ni con tus partituras de forma que se te pueda reconocer.
          </p>
        </section>

        <section aria-labelledby="data-use-copyright">
          <h2 id="data-use-copyright">Derechos de autor de las partituras</h2>
          <p>
            Sube solo partituras que puedas usar: de dominio público, tuyas o con permiso de quien
            tiene sus derechos. Una partitura impresa puede tener derechos de autor por la obra, por
            el arreglo o por la edición, aunque la música sea antigua.
          </p>
          <p>
            Subirla no cede sus derechos a Cadenza ni a nadie: siguen siendo de quien los tenga.
            Cadenza no publica ni comparte las imágenes que subes: las ves tú desde tu cuenta y el
            equipo del proyecto, que las necesita para investigar. Con tu permiso, se usan solo
            dentro del proyecto, para la investigación y para entrenar los modelos; lo que se
            publique serán cifras de conjunto, no las partituras.
          </p>
          <p>
            Si alguien con derechos sobre una partitura que se ha subido pide retirarla, el equipo
            del proyecto la borrará.
          </p>
        </section>

        <section aria-labelledby="data-use-withdraw">
          <h2 id="data-use-withdraw">Dar y retirar el permiso</h2>
          <p>
            Para crear una cuenta hace falta darlo. Después puedes retirarlo cuando quieras desde
            «Tu cuenta», con el mismo interruptor con el que lo vuelves a dar, y seguir usando
            Cadenza igual. Desde que lo retiras, tus datos dejan de usarse para investigar y para
            entrenar los modelos; lo que ya forme parte de un resultado publicado o de un modelo
            entrenado no se puede deshacer.
          </p>
          <p>
            Si este texto cambia, el permiso que diste para esta versión deja de valer hasta que
            leas el nuevo y lo vuelvas a dar.
          </p>
          <p>
            Este permiso es el de las cuentas que se crean en el registro. Si tu cuenta te la dio el
            equipo del proyecto para participar en el estudio, el uso de tus datos se rige por el
            consentimiento que firmaste para el estudio.
          </p>
        </section>

        <section aria-labelledby="data-use-questions">
          <h2 id="data-use-questions">Dudas</h2>
          <p>Para cualquier duda sobre tus datos, habla con el equipo del proyecto.</p>
        </section>

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
