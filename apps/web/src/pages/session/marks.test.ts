import { afterEach, describe, expect, it } from "vitest";
import { markDrawn, markReceived, markSent, timeStage } from "./marks";

afterEach(() => {
  performance.clearMarks();
  performance.clearMeasures();
});

describe("marcas de rendimiento de una orden (#275)", () => {
  it("marca el envío, la respuesta y el dibujo, y mide la orden entera", () => {
    const order = markSent("edit", 3, "web-0123456789abcdef0123");
    markReceived(order, "s1", 4);
    markDrawn("s1", 4);

    const sent = performance.getEntriesByName(`${order}:enviar`, "mark")[0] as PerformanceMark;
    expect(sent.detail).toEqual({
      kind: "edit",
      baseSeq: 3,
      requestId: "web-0123456789abcdef0123",
    });
    expect(performance.getEntriesByName(`${order}:recibir`, "mark")).toHaveLength(1);
    expect(performance.getEntriesByName(`${order}:dibujado`, "mark")).toHaveLength(1);
    expect(performance.getEntriesByName(`${order}:servidor`, "measure")).toHaveLength(1);
    expect(performance.getEntriesByName(order, "measure")).toHaveLength(1);
  });

  it("un dibujo que no creó una orden no mide nada, y cada estado se mide una vez", () => {
    markDrawn("s1", 9);
    expect(performance.getEntriesByType("measure")).toHaveLength(0);

    const order = markSent("undo", 9, "web-1");
    markReceived(order, "s1", 10);
    markDrawn("otra", 10);
    expect(performance.getEntriesByName(order, "measure")).toHaveLength(0);
    markDrawn("s1", 10);
    markDrawn("s1", 10);
    expect(performance.getEntriesByName(order, "measure")).toHaveLength(1);
  });
});

describe("etapas del dibujo de un estado (#276)", () => {
  it("mide cada etapa con su sesión y su seq, y devuelve lo que hace", () => {
    const result = timeStage("leer", "s1", 4, () => 7);
    timeStage("dibujar", "s1", 4, () => undefined);
    timeStage("mapa", "s1", 4, () => undefined);

    expect(result).toBe(7);
    const measures = performance.getEntriesByType("measure") as PerformanceMeasure[];
    expect(measures.map((entry) => entry.name)).toEqual([
      "cadenza:dibujo:leer",
      "cadenza:dibujo:dibujar",
      "cadenza:dibujo:mapa",
    ]);
    expect(measures[0]?.detail).toEqual({ sessionId: "s1", seq: 4 });
    expect(measures.every((entry) => entry.duration >= 0)).toBe(true);
  });

  it("si la etapa falla, la mide igual y deja pasar el error", () => {
    expect(() =>
      timeStage("dibujar", "s1", 5, () => {
        throw new Error("OSMD");
      }),
    ).toThrow("OSMD");
    expect(performance.getEntriesByName("cadenza:dibujo:dibujar", "measure")).toHaveLength(1);
  });
});
