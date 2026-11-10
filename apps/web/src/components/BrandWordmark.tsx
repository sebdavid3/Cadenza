import "./brand-wordmark.css";

// La palabra CADENZA en una rejilla de celdas cuadradas (#383): 7 filas de alto, astas de 2
// celdas, trazos horizontales de 1 y 1 celda entre letras; 53 × 7 en total. Las rutas son las de
// los SVG maestros de docs/marca/ en unidades de celda, con la regla de relleno por defecto y los
// huecos en sentido contrario. El dibujo lo decidió el responsable: no se retoca.
const LETTERS =
  "M12 4H13V2H12V1H10V2H9V4H11ZM13 5H9V7H7V2H8V1H9V0H13V1H14V2H15V7H13V6ZM23 5V0H29V1H25V3H28V4H25V6H29V7H23V6ZM4 0H6V1H2V6H6V7H1V6H0V1H1V0H3ZM18 3V6H20V1H18V2ZM19 0H21V1H22V6H21V7H16V0H18ZM30 0H32V1H33V2H34V3H35V0H37V7H35V5H34V4H33V3H32V7H30V1ZM43 2V3H42V4H41V5H40V6H44V7H38V5H39V4H40V3H41V2H42V1H38V0H44V2ZM47 2V7H45V2H46V1H47V0H51V1H52V2H53V7H51V2H50V1H48V2Z";
// El punto de 2 × 2 celdas que sustituye al travesaño de la A final: el calderón.
const DOT = "M49 5H48V3H50V5Z";

/**
 * El logo de Cadenza: la palabra dibujada en la rejilla, con la A final convertida en calderón.
 * Las letras van del color del texto y el punto, en violeta, es lo único que pide «te toca a ti».
 * Es decorativo: el nombre accesible lo pone el enlace que lo lleva. Mide lo que diga la variable
 * `--brand-cell` (una celda en píxeles enteros, para que el bitmap no se difumine).
 */
export function BrandWordmark() {
  return (
    <svg
      className="brand-wordmark"
      viewBox="0 0 53 7"
      shapeRendering="crispEdges"
      aria-hidden="true"
      focusable="false"
    >
      <path fill="currentColor" d={LETTERS} />
      <path className="brand-wordmark__dot" d={DOT} />
    </svg>
  );
}
