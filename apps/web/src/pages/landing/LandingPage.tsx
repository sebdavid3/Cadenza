import { Link } from "react-router";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { SiteHeader } from "../../components/SiteHeader";
import { REPOSITORY_URL } from "../../config";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { CORRECTED, OMR_READING } from "./incipit";
import { IncipitDemo } from "./IncipitDemo";
import { IncipitScan } from "./IncipitScan";
import { IncipitStaff } from "./IncipitStaff";
import "./landing.css";

const STEPS = [
  {
    title: "Sube las imágenes",
    text: "Fotografías o escaneos de partituras impresas, en PNG o JPEG de hasta 20 MB. Puedes subir varias: se transcriben en cola, una tras otra.",
    figure: <IncipitScan measures={CORRECTED} className="step__scan" />,
    caption: "La imagen",
  },
  {
    title: "HOMR transcribe",
    text: "Un motor de reconocimiento óptico de música lee la imagen y propone la partitura como notación. Cada imagen abre una sesión de trabajo.",
    figure: <IncipitStaff measures={OMR_READING} />,
    caption: "Lo que lee el motor",
  },
  {
    title: "Las reglas señalan la duda",
    text: "Un validador revisa la duración de cada compás, la armadura, el registro y otras reglas musicales, y marca lo sospechoso. No cambia nada por su cuenta.",
    figure: <IncipitStaff measures={OMR_READING} flagged />,
    caption: "Compás 3: cuatro tiempos en un 3/4",
  },
  {
    title: "Tú decides",
    text: "Corriges sobre la notación. Cada cambio queda registrado, con su autor y su orden, y se puede deshacer. La corrección en el navegador está en construcción.",
    figure: <IncipitStaff measures={CORRECTED} />,
    caption: "Dos duraciones corregidas",
  },
];

export function LandingPage() {
  useDocumentTitle();

  return (
    <>
      <SiteHeader />
      <main className="landing">
        <section className="hero" aria-labelledby="hero-title">
          <h1 id="hero-title" className="hero__title">
            De píxel <span>a nota.</span>
          </h1>
          <div className="hero__copy">
            <p className="hero__lead">
              Cadenza convierte la imagen de una partitura impresa en notación editable. Un motor de
              reconocimiento óptico propone la transcripción, unas reglas musicales señalan los
              compases que no cuadran y tú decides cada corrección.
            </p>
            <div className="hero__actions">
              <Link className="button button--primary" to="/entrar">
                Entrar
                <PixelIcon name="arrow-right" />
              </Link>
              <a className="label hero__code" href={REPOSITORY_URL}>
                Ver el código
              </a>
            </div>
            <p className="hero__note">
              No hay registro abierto: las cuentas las crea el equipo del proyecto.
            </p>
          </div>
        </section>

        <IncipitDemo />

        <section id="como-funciona" className="steps" aria-labelledby="steps-title">
          <h2 id="steps-title" className="section-title">
            Cómo funciona
          </h2>
          <ol className="steps__list">
            {STEPS.map((step, index) => (
              <li key={step.title} className="step">
                <span className="step__number" aria-hidden="true">
                  {index + 1}
                </span>
                <div className="step__text">
                  <h3 className="step__title">{step.title}</h3>
                  <p>{step.text}</p>
                </div>
                <figure className="step__figure">
                  {step.figure}
                  <figcaption className="label">{step.caption}</figcaption>
                </figure>
              </li>
            ))}
          </ol>
        </section>

        <section id="alcance" className="scope" aria-labelledby="scope-title">
          <h2 id="scope-title" className="section-title">
            Qué lee hoy
          </h2>
          <p className="scope__intro">
            Cadenza se ha probado con incipits impresos de una sola voz del corpus PrIMuS. Lo que no
            se ha evaluado, no lo prometemos.
          </p>
          <div className="scope__columns">
            <div className="scope__column">
              <h3 className="scope__heading">Sí</h3>
              <ul>
                <li>Partituras impresas</li>
                <li>Una voz en un pentagrama</li>
                <li>Imágenes PNG o JPEG de hasta 20 MB, una página por imagen</li>
                <li>Exportación a MusicXML y MIDI (desde el navegador, próximamente)</li>
              </ul>
            </div>
            <div className="scope__column scope__column--no">
              <h3 className="scope__heading">Todavía no</h3>
              <ul>
                <li>Manuscritos</li>
                <li>Polifonía densa</li>
                <li>PDF y documentos de varias páginas</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="access" aria-labelledby="access-title">
          <h2 id="access-title" className="access__title">
            Entra a trabajar.
          </h2>
          <p className="access__text">
            Si el equipo del proyecto te dio una cuenta, entra con tu usuario y tu contraseña. No
            hay registro abierto ni recuperación de contraseña por correo: las cuentas las crea un
            investigador del proyecto.
          </p>
          <div className="access__actions">
            <Link className="button access__button" to="/entrar">
              Entrar
              <PixelIcon name="arrow-right" />
            </Link>
            <a className="label access__code" href={REPOSITORY_URL}>
              Código abierto en GitHub
            </a>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <p className="site-footer__specimen" aria-hidden="true">
          <span>Cadenza</span>
          <span>Cadenza</span>
          <span>Cadenza</span>
          <span>Cadenza</span>
        </p>
        <p className="label">
          Cadenza · digitalización asistida de partituras ·{" "}
          <a href={REPOSITORY_URL}>github.com/sebdavid3/Cadenza</a>
        </p>
      </footer>
    </>
  );
}
