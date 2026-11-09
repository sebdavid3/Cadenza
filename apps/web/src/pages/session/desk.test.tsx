import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { DeskDivider } from "./DeskDivider";
import { SHARE_DEFAULT, SHARE_MAX, SHARE_MIN } from "./deskShare";
import { ScanFigure } from "./ScanFigure";
import { readStored, writeStored } from "./storage";
import sessionCss from "./session.css?raw";

/** Mesa de corrección (#341): la imagen original con su zoom y el divisor que reparte el ancho. */

const blob = new Blob([new Uint8Array([1, 2])], { type: "image/png" });

afterEach(() => {
  localStorage.clear();
});

describe("la imagen original", () => {
  const tools = () => screen.getByRole("group", { name: "Zoom de la imagen" });
  const tool = (name: string) => within(tools()).getByRole("button", { name });
  const frame = () => screen.getByRole("group", { name: /^Imagen original:/ });
  const readout = () => within(tools()).getByRole("status");

  it("se abre ajustada al ancho, con sus controles de zoom", () => {
    render(<ScanFigure blob={blob} status="ready" />);

    expect(screen.getByRole("heading", { name: "Imagen original" })).toBeInTheDocument();
    expect(screen.getByAltText("Imagen original de la partitura")).toBeInTheDocument();
    expect(tool("Ajustar al ancho")).toHaveAttribute("aria-pressed", "true");
    expect(tool("Página entera")).toHaveAttribute("aria-pressed", "false");
    expect(readout()).toHaveTextContent("100 %");
    expect(frame()).toHaveAttribute("data-zoom", "width");
    // El marco se enfoca para moverlo con las flechas.
    expect(frame()).toHaveAttribute("tabindex", "0");
  });

  it("acerca por pasos hasta el 400 % y aleja hasta la página entera", () => {
    render(<ScanFigure blob={blob} status="ready" />);

    fireEvent.click(tool("Acercar"));
    expect(readout()).toHaveTextContent("150 %");
    expect(frame()).toHaveAttribute("data-zoom", "zoom");
    expect(frame().style.getPropertyValue("--scan-zoom")).toBe("1.5");
    expect(tool("Ajustar al ancho")).toHaveAttribute("aria-pressed", "false");

    for (let step = 0; step < 5; step += 1) fireEvent.click(tool("Acercar"));
    expect(readout()).toHaveTextContent("400 %");
    expect(tool("Acercar")).toHaveAttribute("aria-disabled", "true");

    fireEvent.click(tool("Ajustar al ancho"));
    fireEvent.click(tool("Alejar"));
    expect(readout()).toHaveTextContent("Página");
    expect(tool("Página entera")).toHaveAttribute("aria-pressed", "true");
    expect(frame()).toHaveAttribute("data-zoom", "page");
    expect(tool("Alejar")).toHaveAttribute("aria-disabled", "true");
  });

  it("con el marco enfocado, + y − acercan y alejan, y 0 vuelve al ancho", () => {
    render(<ScanFigure blob={blob} status="ready" />);

    fireEvent.keyDown(frame(), { key: "+" });
    fireEvent.keyDown(frame(), { key: "+" });
    expect(readout()).toHaveTextContent("200 %");
    fireEvent.keyDown(frame(), { key: "-" });
    expect(readout()).toHaveTextContent("150 %");
    fireEvent.keyDown(frame(), { key: "0" });
    expect(readout()).toHaveTextContent("100 %");
  });

  it("Ctrl y la rueda acercan y alejan sin desplazar la página", () => {
    render(<ScanFigure blob={blob} status="ready" />);

    const zoomIn = new WheelEvent("wheel", { deltaY: -100, ctrlKey: true, cancelable: true });
    act(() => {
      frame().dispatchEvent(zoomIn);
    });
    expect(zoomIn.defaultPrevented).toBe(true);
    expect(readout()).toHaveTextContent("150 %");

    const scroll = new WheelEvent("wheel", { deltaY: 100, cancelable: true });
    act(() => {
      frame().dispatchEvent(scroll);
    });
    expect(scroll.defaultPrevented).toBe(false);
    expect(readout()).toHaveTextContent("150 %");
  });

  it("mientras carga, los controles esperan", () => {
    render(<ScanFigure blob={null} status="loading" />);

    expect(screen.getByText("Cargando la imagen…")).toBeInTheDocument();
    expect(tool("Acercar")).toHaveAttribute("aria-disabled", "true");
    expect(tool("Alejar")).toHaveAttribute("aria-disabled", "true");
  });

  it("si falla, lo dice", () => {
    render(<ScanFigure blob={null} status="error" />);

    expect(screen.getByText("No se pudo cargar la imagen original.")).toBeInTheDocument();
  });

  it("en una columna se puede ocultar para dejar sitio a la partitura", () => {
    const { container } = render(<ScanFigure blob={blob} status="ready" />);
    const toggle = screen.getByRole("button", { name: "Ocultar la imagen" });

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveTextContent("Ocultar");
    fireEvent.click(toggle);

    const shown = screen.getByRole("button", { name: "Ver la imagen" });
    expect(shown).toHaveAttribute("aria-expanded", "false");
    expect(container.querySelector(".sheet--scan")).toHaveAttribute("data-collapsed", "true");
  });
});

describe("el divisor entre la imagen y la partitura", () => {
  function Desk() {
    const [share, setShare] = useState(SHARE_DEFAULT);
    return (
      <div
        data-testid="mesa"
        ref={(element) => {
          if (element) {
            element.getBoundingClientRect = () => DOMRect.fromRect({ x: 100, width: 1000 });
          }
        }}
      >
        <DeskDivider share={share} onShare={setShare} controls="imagen" />
      </div>
    );
  }
  const separator = () => screen.getByRole("separator", { name: "Ancho de la imagen" });

  it("es un separador vertical con su valor", () => {
    render(<Desk />);

    expect(separator()).toHaveAttribute("aria-orientation", "vertical");
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_DEFAULT * 100));
    expect(separator()).toHaveAttribute("aria-valuemin", String(SHARE_MIN * 100));
    expect(separator()).toHaveAttribute("aria-valuemax", String(SHARE_MAX * 100));
    expect(separator()).toHaveAttribute("aria-controls", "imagen");
    expect(separator()).toHaveAttribute("tabindex", "0");
  });

  it("se mueve con las flechas, Inicio y Fin, sin salirse de sus límites", () => {
    render(<Desk />);

    fireEvent.keyDown(separator(), { key: "ArrowRight" });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_DEFAULT * 100 + 5));
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_DEFAULT * 100 - 5));
    fireEvent.keyDown(separator(), { key: "Home" });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_MIN * 100));
    fireEvent.keyDown(separator(), { key: "ArrowLeft" });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_MIN * 100));
    fireEvent.keyDown(separator(), { key: "End" });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_MAX * 100));
  });

  it("se arrastra con el puntero sobre el ancho de la mesa", () => {
    render(<Desk />);

    fireEvent.pointerDown(separator(), { clientX: 520, pointerId: 1, button: 0 });
    fireEvent.pointerMove(separator(), { clientX: 650, pointerId: 1 });
    expect(separator()).toHaveAttribute("aria-valuenow", "55");
    // Más allá del límite, se queda en él.
    fireEvent.pointerMove(separator(), { clientX: 1050, pointerId: 1 });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_MAX * 100));
    fireEvent.pointerUp(separator(), { clientX: 1050, pointerId: 1 });
    fireEvent.pointerMove(separator(), { clientX: 300, pointerId: 1 });
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_MAX * 100));
  });

  it("con doble clic vuelve al reparto inicial", () => {
    render(<Desk />);

    fireEvent.keyDown(separator(), { key: "End" });
    fireEvent.doubleClick(separator());
    expect(separator()).toHaveAttribute("aria-valuenow", String(SHARE_DEFAULT * 100));
  });
});

describe("lo que la mesa recuerda en el navegador", () => {
  it("guarda y lee un valor, y no falla si el almacenamiento no está", () => {
    writeStored("prueba", "valor");
    expect(readStored("prueba")).toBe("valor");

    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("bloqueado");
      },
    });
    try {
      expect(readStored("prueba")).toBeNull();
      expect(() => {
        writeStored("prueba", "otro");
      }).not.toThrow();
    } finally {
      if (original) Object.defineProperty(window, "localStorage", original);
    }
  });
});

describe("la página de la mesa no se alarga (#355)", () => {
  /** Las reglas de un selector en la hoja de la vista, tal como están escritas. */
  const rulesOf = (selector: string) =>
    [...sessionCss.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
      .filter(([, selectors]) =>
        (selectors ?? "")
          .replace(/\/\*[\s\S]*?\*\//g, "")
          .split(",")
          .map((part) => part.trim())
          .includes(selector),
      )
      .map(([, , body]) => body ?? "");

  it("el panel de la partitura, que se desplaza por dentro, contiene a sus hijos posicionados", () => {
    // Si no, los textos ocultos para el lector de pantalla del pie (`position: absolute`) toman
    // un bloque contenedor fuera del panel, que no los recorta, y alargan la página entera con un
    // espacio en blanco bajo la mesa.
    const rules = rulesOf(".session--desk .session__sheets > .sheet--notation").join("\n");
    expect(rules).toMatch(/overflow-y:\s*auto/);
    expect(rules).toMatch(/position:\s*relative/);
  });
});
