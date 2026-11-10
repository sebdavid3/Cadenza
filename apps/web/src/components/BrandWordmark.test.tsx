import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { SessionTopBar } from "../pages/session/SessionHeader";
import { ANA, resetAuth, signInAs } from "../test/auth-helpers";
import { AppLayout } from "./AppLayout";
import { BrandWordmark } from "./BrandWordmark";
import brandCss from "./brand-wordmark.css?raw";
import { SiteHeader } from "./SiteHeader";

/**
 * El logo de Cadenza (#383): la palabra dibujada en una rejilla de 53 × 7 celdas. «#» es una celda
 * de las letras y «o», del punto violeta: la A final cambia el travesaño por el punto, que la
 * convierte en un calderón. El dibujo lo decidió el responsable; no se retoca.
 */
const DRAWING = [
  ".#####...####...#####..######.##...##.######...####..",
  "##......##..##..##..##.##.....###..##.....##..##..##.",
  "##.....##....##.##..##.##.....####.##....##..##....##",
  "##.....##....##.##..##.#####..##.####...##...##.oo.##",
  "##.....########.##..##.##.....##..###..##....##.oo.##",
  "##.....##....##.##..##.##.....##...##.##.....##....##",
  ".#####.##....##.#####..######.##...##.######.##....##",
];

type Point = readonly [number, number];

/** Los contornos de una ruta hecha solo de M, H, V y Z absolutas, como las del logo. */
function contours(d: string): Point[][] {
  const tokens = d.match(/[MHVZ]|-?\d+(?:\.\d+)?/g) ?? [];
  const result: Point[][] = [];
  let current: Point[] = [];
  let x = 0;
  let y = 0;
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (token === "M") {
      x = Number(tokens[++i]);
      y = Number(tokens[++i]);
      current = [[x, y]];
    } else if (token === "H") {
      x = Number(tokens[++i]);
      current.push([x, y]);
    } else if (token === "V") {
      y = Number(tokens[++i]);
      current.push([x, y]);
    } else if (token === "Z") {
      result.push(current);
      current = [];
    } else {
      throw new Error(`orden inesperada en la ruta: ${token ?? ""}`);
    }
  }
  return result;
}

/** Si el centro de la celda queda dentro de la ruta, con la regla de relleno por defecto. */
function filled(paths: Point[][], column: number, row: number): boolean {
  const px = column + 0.5;
  const py = row + 0.5;
  let winding = 0;
  for (const path of paths) {
    path.forEach(([x1, y1], index) => {
      const [x2, y2] = path[(index + 1) % path.length] ?? [x1, y1];
      if ((y1 <= py && py < y2) || (y2 <= py && py < y1)) {
        const crossing = x1 + ((py - y1) * (x2 - x1)) / (y2 - y1);
        if (crossing > px) winding += y2 > y1 ? 1 : -1;
      }
    });
  }
  return winding !== 0;
}

function drawing(svg: SVGSVGElement): string[] {
  const [letters, dot] = Array.from(svg.querySelectorAll("path")).map((path) =>
    contours(path.getAttribute("d") ?? ""),
  );
  if (!letters || !dot) throw new Error("faltan las rutas del logo");
  return DRAWING.map((line, row) =>
    Array.from(line, (_, column) => {
      if (filled(dot, column, row)) return filled(letters, column, row) ? "!" : "o";
      return filled(letters, column, row) ? "#" : ".";
    }).join(""),
  );
}

function wordmarkIn(element: HTMLElement): SVGSVGElement {
  const svg = element.querySelector<SVGSVGElement>("svg.brand-wordmark");
  if (!svg) throw new Error("no está el logo");
  return svg;
}

describe("el logo (#383)", () => {
  it("es un SVG decorativo de 53 × 7 celdas, nítido y sin foco", () => {
    const { container } = render(<BrandWordmark />);
    const svg = wordmarkIn(container);

    expect(svg).toHaveAttribute("viewBox", "0 0 53 7");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("focusable", "false");
    expect(svg).toHaveAttribute("shape-rendering", "crispEdges");
    expect(svg.querySelectorAll("path")).toHaveLength(2);
  });

  it("dibuja las letras del color del texto y el punto con la clase del violeta", () => {
    const { container } = render(<BrandWordmark />);
    const [letters, dot] = Array.from(wordmarkIn(container).querySelectorAll("path"));

    expect(letters).toHaveAttribute("fill", "currentColor");
    expect(letters).not.toHaveAttribute("class");
    expect(dot).toHaveClass("brand-wordmark__dot");
    expect(dot).not.toHaveAttribute("fill");
  });

  it("dibuja la palabra de la rejilla, con el punto en la A final y sin solapes", () => {
    const { container } = render(<BrandWordmark />);

    expect(drawing(wordmarkIn(container))).toEqual(DRAWING);
  });

  it("su hoja pinta el punto de violeta, de CanvasText con colores forzados, y mide en celdas", () => {
    const css = brandCss.replace(/\s+/g, " ");

    expect(css).toMatch(/\.brand-wordmark__dot \{ fill: var\(--color-accent\); \}/);
    expect(css).toMatch(
      /@media \(forced-colors: active\) \{ \.brand-wordmark__dot \{ fill: CanvasText; \} \}/,
    );
    expect(css).toContain("width: calc(53 * var(--brand-cell");
    expect(css).toContain("height: calc(7 * var(--brand-cell");
    expect(css).toMatch(/display: block;/);
    // El violeta va solo en el punto: ninguna otra regla de la hoja lo usa.
    expect(css.match(/--color-accent/g)).toHaveLength(1);
  });

  it("deja el tamaño a quien lo pone: una clase propia se suma a la suya", () => {
    const { container } = render(<BrandWordmark className="site-footer__word" />);

    expect(wordmarkIn(container)).toHaveClass("brand-wordmark", "site-footer__word");
  });
});

describe("la marca de las cabeceras (#383)", () => {
  afterEach(() => {
    resetAuth();
  });

  /** El enlace de la marca muestra el logo y ya no el texto «Cadenza», con su nombre accesible. */
  function expectBrand(banner: HTMLElement, name: string) {
    const link = within(banner).getByRole("link", { name });
    expect(link.textContent).toBe("");
    expect(wordmarkIn(link)).toBeInTheDocument();
    expect(within(banner).queryByText(/cadenza/i)).toBeNull();
    return link;
  }

  it("la pública lleva al inicio", () => {
    render(
      <MemoryRouter>
        <SiteHeader />
      </MemoryRouter>,
    );

    const link = expectBrand(screen.getByRole("banner"), "Cadenza, inicio");
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveClass("site-header__brand");
  });

  it("la de la zona privada lleva a la página pública", () => {
    signInAs(ANA);
    const router = createMemoryRouter(
      [
        {
          element: <AppLayout />,
          children: [{ path: "/transcripcion", element: <p>Las sesiones</p> }],
        },
      ],
      { initialEntries: ["/transcripcion"] },
    );
    render(<RouterProvider router={router} />);

    const link = expectBrand(screen.getByRole("banner"), "Cadenza, página pública");
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveClass("app-header__brand");
  });

  it("la de la vista de una sesión lleva a la página pública", () => {
    signInAs(ANA);
    render(
      <MemoryRouter>
        <SessionTopBar />
      </MemoryRouter>,
    );

    const link = expectBrand(screen.getByRole("banner"), "Cadenza, página pública");
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveClass("session__brand");
  });
});
