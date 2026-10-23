import { Link } from "react-router";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { SiteHeader } from "../../components/SiteHeader";
import { registrationEnabled, REPOSITORY_URL } from "../../config";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { STEPS } from "./content";
import { CORRECTED, OMR_READING } from "./incipit";
import { IncipitDemo } from "./IncipitDemo";
import { IncipitScan } from "./IncipitScan";
import { IncipitStaff } from "./IncipitStaff";
import "./landing.css";

// Las figuras de los pasos: el mismo incipit sintético en cada momento del proceso.
const STEP_FIGURES = [
  <IncipitScan key="imagen" measures={CORRECTED} className="step__scan" />,
  <IncipitStaff key="lectura" measures={OMR_READING} />,
  <IncipitStaff key="hallazgo" measures={OMR_READING} mark="flagged" />,
  <IncipitStaff key="correccion" measures={CORRECTED} mark="resolved" />,
];

const SPECIMEN_SIZES = ["96 px", "48 px", "24 px", "12 px"];

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
              {registrationEnabled() ? (
                <>
                  ¿Sin cuenta? <Link to="/registro">Créala</Link>: queda pendiente hasta que el
                  equipo del proyecto decida activarla.
                </>
              ) : (
                "No hay registro abierto: las cuentas las crea el equipo del proyecto."
              )}
            </p>
          </div>
        </section>

        <IncipitDemo />

        <section id="como-funciona" className="steps" aria-labelledby="steps-title">
          <h2 id="steps-title" className="section-title">
            Cómo funciona
          </h2>
          <p className="steps__note">
            Las figuras son ilustraciones con el mismo incipit sintético de arriba.
          </p>
          <ol className="steps__list" role="list">
            {STEPS.map((step, index) => (
              <li key={step.title} id={`paso-${String(index + 1)}`} className="step">
                <span className="step__number" aria-hidden="true">
                  {index + 1}
                </span>
                <div className="step__text">
                  <h3 className="step__title">{step.title}</h3>
                  <p>{step.text}</p>
                </div>
                <figure className="step__figure">
                  {STEP_FIGURES[index]}
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
            <section className="scope__column" aria-labelledby="scope-tested">
              <h3 id="scope-tested" className="scope__heading">
                Probado
              </h3>
              <ul>
                <li>Incipits y fragmentos impresos</li>
                <li>Una voz en un pentagrama</li>
                <li>Imágenes PNG o JPEG de hasta 20 MB, una por sesión</li>
              </ul>
            </section>
            <section className="scope__column scope__column--untested" aria-labelledby="scope-no">
              <div className="scope__block">
                <h3 id="scope-no" className="scope__heading">
                  Sin evaluar
                </h3>
                <ul>
                  <li>Manuscritos</li>
                  <li>Más de una voz o varios pentagramas</li>
                  <li>Fotografías de partituras</li>
                </ul>
              </div>
            </section>
          </div>
          <div className="scope__notes">
            <p>
              Las reglas no lo detectan todo: una nota con la altura equivocada en un compás que
              suma bien pasa sin señal. Revisa toda la transcripción, no solo lo marcado.
            </p>
            <p>No admite PDF ni documentos de varias páginas: una imagen por sesión.</p>
          </div>
        </section>

        <section className="access" aria-labelledby="access-title">
          <h2 id="access-title" className="access__title">
            Entra a trabajar.
          </h2>
          <p className="access__text">
            {registrationEnabled()
              ? "Entra con tu usuario y tu contraseña. Si aún no tienes cuenta, créala: solo pide un usuario y una contraseña, sin correo, y queda pendiente hasta que un investigador del proyecto decida activarla. No hay recuperación de contraseña por correo."
              : "Si el equipo del proyecto te dio una cuenta, entra con tu usuario y tu contraseña. No hay registro abierto ni recuperación de contraseña por correo: las cuentas las crea un investigador del proyecto."}
          </p>
          <div className="access__actions">
            <Link className="button access__button" to="/entrar">
              Entrar
              <PixelIcon name="arrow-right" />
            </Link>
            {registrationEnabled() && (
              <Link className="label access__code access__register" to="/registro">
                Crear una cuenta
              </Link>
            )}
            <a className="label access__code" href={REPOSITORY_URL}>
              Código abierto en GitHub
            </a>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <ul className="site-footer__specimen" aria-hidden="true">
          {SPECIMEN_SIZES.map((size) => (
            <li key={size}>
              <span className="site-footer__word">Cadenza</span>
              <span className="label site-footer__size">{size}</span>
            </li>
          ))}
        </ul>
        <p className="label">
          Cadenza · digitalización asistida de partituras ·{" "}
          <a href={REPOSITORY_URL}>github.com/sebdavid3/Cadenza</a>
        </p>
      </footer>
    </>
  );
}
