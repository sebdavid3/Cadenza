import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom no implementa el contexto 2D del canvas: las vistas que pintan deben tolerar null.
Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  value: () => null,
  configurable: true,
  writable: true,
});
