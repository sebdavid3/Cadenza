import type { ReactNode } from "react";
import { STORED_DATA } from "./consent";

type Layout = "page" | "inline";

/**
 * Un apartado del texto. En la página es una banda con su título a la izquierda y el texto a la
 * derecha, y una región con nombre; desplegado en el registro es un bloque más, sin región, para
 * no llenar el formulario de puntos de referencia.
 */
function Part({
  id,
  title,
  layout,
  children,
}: {
  id: string;
  title: string;
  layout: Layout;
  children: ReactNode;
}) {
  if (layout === "inline") {
    return (
      <div className="consent-full__part">
        <h2>{title}</h2>
        {children}
      </div>
    );
  }
  return (
    <section className="data-use__band" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      <div className="data-use__body">{children}</div>
    </section>
  );
}

/**
 * El texto completo del permiso de uso de los datos (#378, ADR-0065), versión del 9 de noviembre
 * de 2026, el mismo en la página `/uso-de-los-datos` y desplegado en el registro (#397). Lo aprobó
 * el responsable del proyecto el 2026-11-09: si cambia, cambia también `DATA_CONSENT_VERSION`.
 */
export function DataUseText({ layout }: { layout: Layout }) {
  return (
    <>
      <Part id="data-use-what" title="Qué se guarda" layout={layout}>
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
      </Part>

      <Part id="data-use-why" title="Para qué, con tu permiso" layout={layout}>
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
      </Part>

      <Part id="data-use-copyright" title="Derechos de autor de las partituras" layout={layout}>
        <p>
          Sube solo partituras que puedas usar: de dominio público, tuyas o con permiso de quien
          tiene sus derechos. Una partitura impresa puede tener derechos de autor por la obra, por
          el arreglo o por la edición, aunque la música sea antigua.
        </p>
        <p>
          Subirla no cede sus derechos a Cadenza ni a nadie: siguen siendo de quien los tenga.
          Cadenza no publica ni comparte las imágenes que subes: las ves tú desde tu cuenta y el
          equipo del proyecto, que las necesita para investigar. Con tu permiso, se usan solo dentro
          del proyecto, para la investigación y para entrenar los modelos; lo que se publique serán
          cifras de conjunto, no las partituras.
        </p>
        <p>
          Si alguien con derechos sobre una partitura que se ha subido pide retirarla, el equipo del
          proyecto la borrará.
        </p>
      </Part>

      <Part id="data-use-withdraw" title="Dar y retirar el permiso" layout={layout}>
        <p>
          Para crear una cuenta hace falta darlo. Después puedes retirarlo cuando quieras desde «Tu
          cuenta», con el mismo interruptor con el que lo vuelves a dar, y seguir usando Cadenza
          igual. Desde que lo retiras, tus datos dejan de usarse para investigar y para entrenar los
          modelos; lo que ya forme parte de un resultado publicado o de un modelo entrenado no se
          puede deshacer.
        </p>
        <p>
          Si este texto cambia, el permiso que diste para esta versión deja de valer hasta que leas
          el nuevo y lo vuelvas a dar.
        </p>
        <p>
          Este permiso es el de las cuentas que se crean en el registro. Si tu cuenta te la dio el
          equipo del proyecto para participar en el estudio, el uso de tus datos se rige por el
          consentimiento que firmaste para el estudio.
        </p>
      </Part>

      <Part id="data-use-questions" title="Dudas" layout={layout}>
        <p>Para cualquier duda sobre tus datos, habla con el equipo del proyecto.</p>
      </Part>
    </>
  );
}
