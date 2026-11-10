import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccessPanel } from "./AccessPanel";
import { PORTRAIT_STORAGE_KEY } from "./portraits";

// Un panel de 600 × 400 px: 120 × 80 celdas de 5 px.
const CELLS = 120 * 80;

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

const requested: string[] = [];

/** Una imagen que «carga» en cuanto recibe su origen. */
class LoadedImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  decoding = "auto";
  naturalWidth = 320;
  naturalHeight = 324;
  set src(value: string) {
    requested.push(value);
    queueMicrotask(() => this.onload?.());
  }
}

/** `matchMedia` con las consultas que se dan por ciertas. */
function stubMedia(...matching: string[]) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: matching.includes(query),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

/** Fotogramas que la prueba lanza a mano, con su marca de tiempo. */
function stubFrames() {
  const pending: FrameRequestCallback[] = [];
  const cancel = vi.fn();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    pending.push(callback);
    return pending.length;
  });
  vi.stubGlobal("cancelAnimationFrame", cancel);
  const frame = (time: number) => {
    act(() => {
      pending.shift()?.(time);
    });
  };
  return { frame, cancel };
}

async function imageLoaded() {
  await act(async () => {
    await Promise.resolve();
  });
}

beforeEach(() => {
  requested.length = 0;
  vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(600);
  vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(400);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("panel del acceso", () => {
  it("el titular es el h1 y el retrato es decorativo para el lector de pantalla", () => {
    render(<AccessPanel title="Entrar" />);

    expect(screen.getByRole("heading", { level: 1, name: "Entrar" })).toBeVisible();
    const figure = document.querySelector("figure");
    expect(figure).toHaveAttribute("aria-hidden", "true");
    expect(figure?.querySelector("canvas")).not.toBeNull();
  });

  it("sin contexto 2D no pide el retrato: se queda la trama, sin rotular a nadie", async () => {
    vi.stubGlobal("Image", LoadedImage);

    render(<AccessPanel title="Entrar" />);
    await imageLoaded();

    expect(requested).toEqual([]);
    expect(document.querySelector("figcaption")).toBeNull();
  });

  it("con colores forzados tampoco lo pide", async () => {
    stubCanvas();
    stubMedia("(forced-colors: active)");
    vi.stubGlobal("Image", LoadedImage);

    render(<AccessPanel title="Entrar" />);
    await imageLoaded();

    expect(requested).toEqual([]);
    expect(document.querySelector("figcaption")).toBeNull();
  });

  it("con movimiento reducido dibuja el retrato que toca de una vez y lo rotula", async () => {
    window.localStorage.setItem(PORTRAIT_STORAGE_KEY, "0");
    const drawn = stubCanvas();
    stubMedia("(prefers-reduced-motion: reduce)");
    vi.stubGlobal("Image", LoadedImage);

    render(<AccessPanel title="Entrar" />);
    await imageLoaded();

    expect(screen.getByText("Wolfgang Amadeus Mozart")).toBeInTheDocument();
    expect(screen.getByText(/1756–1791 · Óleo de Barbara Krafft, 1819/)).toBeInTheDocument();
    expect(drawn.dots).toBe(CELLS);
    expect(window.localStorage.getItem(PORTRAIT_STORAGE_KEY)).toBe("1");
  });

  it("se imprime por bandas: cada fila una sola vez, y el pie al terminar", async () => {
    const drawn = stubCanvas();
    stubMedia();
    const { frame } = stubFrames();
    vi.stubGlobal("Image", LoadedImage);

    render(<AccessPanel title="Entrar" />);
    await imageLoaded();

    frame(1000); // primer salto: 3 de las 80 filas (80 / 28, por arriba)
    expect(drawn.dots).toBe(3 * 120);
    frame(1700); // a mitad: 15 saltos, 43 filas
    expect(drawn.dots).toBe(43 * 120);
    expect(document.querySelector("figcaption")).toBeNull();

    frame(2400); // el último salto
    expect(drawn.dots).toBe(CELLS);
    expect(document.querySelector("figcaption")).not.toBeNull();
  });

  it("al desmontar a mitad de la impresión la cancela", async () => {
    stubCanvas();
    stubMedia();
    const { frame, cancel } = stubFrames();
    vi.stubGlobal("Image", LoadedImage);

    const { unmount } = render(<AccessPanel title="Entrar" />);
    await imageLoaded();
    frame(1000);
    unmount();

    expect(cancel).toHaveBeenCalled();
  });

  it("si la imagen no carga, no rotula a nadie", async () => {
    stubCanvas();
    vi.stubGlobal(
      "Image",
      class extends LoadedImage {
        override set src(value: string) {
          requested.push(value);
          queueMicrotask(() => this.onerror?.());
        }
      },
    );

    render(<AccessPanel title="Entrar" />);
    await imageLoaded();

    expect(requested).toHaveLength(1);
    expect(document.querySelector("figcaption")).toBeNull();
  });

  it("en la misma visita, volver al acceso no cambia de compositor", async () => {
    stubCanvas();
    vi.stubGlobal("Image", LoadedImage);

    const first = render(<AccessPanel title="Entrar" />);
    await imageLoaded();
    const name = document.querySelector(".portrait__name")?.textContent;
    first.unmount();
    render(<AccessPanel title="Crear cuenta" />);
    await imageLoaded();

    expect(name).toBeTruthy();
    expect(document.querySelector(".portrait__name")?.textContent).toBe(name);
  });
});
