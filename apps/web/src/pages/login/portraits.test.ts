import { afterEach, describe, expect, it, vi } from "vitest";
import {
  coverCrop,
  DOT_MAX_RADIUS,
  dotRadius,
  pickPortraitIndex,
  PORTRAIT_STORAGE_KEY,
  PORTRAITS,
  readLastPortrait,
  rememberPortrait,
} from "./portraits";

afterEach(() => {
  window.localStorage.clear();
});

describe("retratos del acceso", () => {
  it("son los cinco compositores acordados, con su fuente servida desde el proyecto", () => {
    expect(PORTRAITS.map((portrait) => portrait.name)).toEqual([
      "Johann Sebastian Bach",
      "Wolfgang Amadeus Mozart",
      "Ludwig van Beethoven",
      "Frédéric Chopin",
      "Clara Schumann",
    ]);
    for (const portrait of PORTRAITS) {
      expect(portrait.src).not.toMatch(/^https?:/);
      expect(portrait.credit).toMatch(/\d{4}$/);
      expect(portrait.focus.x).toBeGreaterThan(0);
      expect(portrait.focus.x).toBeLessThan(1);
      expect(portrait.focus.y).toBeGreaterThan(0);
      expect(portrait.focus.y).toBeLessThan(1);
    }
  });

  it("rota: cada visita muestra el siguiente al último y vuelve al primero al acabar", () => {
    const random = () => 0.99;
    expect(pickPortraitIndex("0", 5, random)).toBe(1);
    expect(pickPortraitIndex("3", 5, random)).toBe(4);
    expect(pickPortraitIndex("4", 5, random)).toBe(0);
  });

  it("en la primera visita, o con un valor que no sirve, empieza por uno al azar", () => {
    expect(pickPortraitIndex(null, 5, () => 0)).toBe(0);
    expect(pickPortraitIndex(null, 5, () => 0.99)).toBe(4);
    expect(pickPortraitIndex("7", 5, () => 0.5)).toBe(2);
    expect(pickPortraitIndex("abc", 5, () => 0.5)).toBe(2);
    expect(pickPortraitIndex("-1", 5, () => 0.5)).toBe(2);
  });

  it("recuerda el último en el navegador y no falla sin almacenamiento", () => {
    rememberPortrait(3);
    expect(window.localStorage.getItem(PORTRAIT_STORAGE_KEY)).toBe("3");
    expect(readLastPortrait()).toBe("3");

    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    expect(readLastPortrait()).toBeNull();
    expect(() => {
      rememberPortrait(1);
    }).not.toThrow();
  });
});

describe("recorte del retrato en el panel", () => {
  const focus = { x: 0.5, y: 0.3 };

  it("cubre el panel sin deformar la imagen", () => {
    const crop = coverCrop(1200, 600, 300, 400, focus);
    expect(crop.sw).toBeCloseTo(300);
    expect(crop.sw / crop.sh).toBeCloseTo(1200 / 600);
    expect(crop.sx).toBe(0);
  });

  it("pone los ojos a un tercio largo del alto y no se sale de la imagen", () => {
    // Panel apaisado: entra todo el ancho y se elige qué franja del alto.
    const crop = coverCrop(1200, 600, 300, 400, focus);
    expect(crop.sy + 0.36 * crop.sh).toBeCloseTo(0.3 * 400);
    // Con los ojos muy arriba, el recorte se queda en el borde superior.
    expect(coverCrop(1200, 600, 300, 400, { x: 0.5, y: 0.02 }).sy).toBe(0);
    // Y con los ojos muy abajo, en el inferior.
    const low = coverCrop(1200, 600, 300, 400, { x: 0.5, y: 0.99 });
    expect(low.sy + low.sh).toBeCloseTo(400);
  });

  it("la hoja puede subir la línea de los ojos (la franja estrecha, bajo el titular)", () => {
    const crop = coverCrop(1200, 600, 300, 400, focus, 0.25);
    expect(crop.sy + 0.25 * crop.sh).toBeCloseTo(0.3 * 400);
  });

  it("en un panel alto entra todo el alto y centra la cara en horizontal", () => {
    const crop = coverCrop(400, 1200, 300, 400, { x: 0.6, y: 0.3 });
    expect(crop.sh).toBeCloseTo(400);
    expect(crop.sy).toBe(0);
    expect(crop.sx + crop.sw / 2).toBeCloseTo(0.6 * 300);
  });
});

describe("radio del punto", () => {
  it("el blanco no lleva punto y el negro el mayor; el área crece con la sombra", () => {
    expect(dotRadius(1)).toBe(0);
    expect(dotRadius(0)).toBeCloseTo(DOT_MAX_RADIUS);
    // Área proporcional a la sombra: un gris medio cubre la mitad del área del punto mayor.
    expect(dotRadius(0.5) ** 2).toBeCloseTo(DOT_MAX_RADIUS ** 2 / 2);
    expect(dotRadius(0.2)).toBeGreaterThan(dotRadius(0.6));
  });

  it("acota luminancias fuera de rango", () => {
    expect(dotRadius(1.4)).toBe(0);
    expect(dotRadius(-0.3)).toBeCloseTo(DOT_MAX_RADIUS);
  });
});
