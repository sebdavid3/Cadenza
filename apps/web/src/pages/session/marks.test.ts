import { afterEach, describe, expect, it } from "vitest";
import { markDrawn, markReceived, markSent } from "./marks";

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
