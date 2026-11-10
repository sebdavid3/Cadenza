import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccessPanel } from "./AccessPanel";
import { PORTRAIT_STORAGE_KEY } from "./portraits";

/** Un contexto 2D mínimo que cuenta los puntos dibujados; la imagen se lee como gris medio. */
function stubCanvas() {
  const drawn = { dots: 0 };
  const context = {
    setTransform: () => undefined,
    fillRect: () => undefined,
    beginPath: () => undefined,
    moveTo: () => undefined,
    arc: () => {
      drawn.dots += 1;
    },
    fill: () => undefined,
    drawImage: () => undefined,
    getImageData: (_x: number, _y: number, width: number, height: number) => ({
      data: new Uint8ClampedArray(width * height * 4).fill(128),
    }),
    fillStyle: "",
    imageSmoothingEnabled: true,
    imageSmoothingQuality: "low",
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => context as unknown as CanvasRenderingContext2D,
  );
  return drawn;
}

/** Una imagen que «carga» en cuanto recibe su origen. */
class LoadedImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  decoding = "auto";
  naturalWidth = 320;
  naturalHeight = 324;
  requested = "";
  set src(value: string) {
    this.requested = value;
    queueMicrotask(() => this.onload?.());
  }
}

beforeEach(() => {
  vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(600);
  vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(400);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("panel del acceso", () => {
  it("el titular es el h1 y el retrato es decorativo para el lector de pantalla", () => {
    render(<AccessPanel title="Entrar" />);

    expect(screen.getByRole("heading", { level: 1, name: "Entrar" })).toBeVisible();
    const figure = document.querySelector("figure");
    expect(figure).toHaveAttribute("aria-hidden", "true");
    expect(figure?.querySelector("canvas")).not.toBeNull();
  });

  it("sin contexto 2D se queda la trama de siempre, sin rotular ningún compositor", () => {
    render(<AccessPanel title="Entrar" />);

    expect(document.querySelector("figcaption")).toBeNull();
  });

  it("dibuja el retrato que toca en la rotación, lo rotula y recuerda cuál fue", async () => {
    window.localStorage.setItem(PORTRAIT_STORAGE_KEY, "0");
    const drawn = stubCanvas();
    vi.stubGlobal("Image", LoadedImage);

    render(<AccessPanel title="Entrar" />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("Wolfgang Amadeus Mozart")).toBeInTheDocument();
    expect(screen.getByText(/1756–1791 · Óleo de Barbara Krafft, 1819/)).toBeInTheDocument();
    // Un punto por celda de 5 px: 120 × 80 en un panel de 600 × 400.
    expect(drawn.dots).toBe(120 * 80);
    expect(window.localStorage.getItem(PORTRAIT_STORAGE_KEY)).toBe("1");
  });

  it("si la imagen no carga, no rotula a nadie", async () => {
    stubCanvas();
    vi.stubGlobal(
      "Image",
      class extends LoadedImage {
        override set src(value: string) {
          this.requested = value;
          queueMicrotask(() => this.onerror?.());
        }
      },
    );

    render(<AccessPanel title="Entrar" />);
    await act(async () => {
      await Promise.resolve();
    });

    expect(document.querySelector("figcaption")).toBeNull();
  });
});
