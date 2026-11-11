import { describe, expect, it } from "vitest";
import consentCss from "./consent.css?raw";

describe("hoja del permiso (#397)", () => {
  it("el texto plegado no se ve aunque el recuadro sea una rejilla", () => {
    // `display: grid` gana al `[hidden]` del navegador: sin esta regla, el texto completo saldría
    // siempre desplegado en el registro, y jsdom no aplica las hojas para notarlo.
    const css = consentCss.replace(/\s+/g, " ");

    expect(css).toMatch(/\.consent-full \{ display: grid;/);
    expect(css).toMatch(/\.consent-full\[hidden\] \{ display: none; \}/);
  });
});
