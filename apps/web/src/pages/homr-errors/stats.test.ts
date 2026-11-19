import { describe, expect, it } from "vitest";
import { group, payload, rate, UNPUBLISHED, values } from "./fixtures";
import {
  beatsValue,
  cadenzaPending,
  cellAlpha,
  durationMatrix,
  findings,
  fold,
  groupInfo,
  historyRows,
  pageList,
  pct,
  shownGroups,
  stepName,
} from "./stats";

describe("las cifras de los errores de HOMR", () => {
  it("dice lo que dicen los datos, como el informe", () => {
    const facts = findings(values());

    expect(facts.map((f) => f.kicker)).toEqual([
      "Qué se corrige",
      "Figura leída",
      "Alteración y armadura",
      "Clave",
    ]);
    expect(facts[0]).toMatchObject({ big: "9\u00a0%" });
    expect(facts[0]?.text).toContain("tenían mal la figura");
    // La figura que peor lee se nombra y se dibuja: nunca la fracción.
    expect(facts[1]).toMatchObject({
      big: "40\u00a0%",
      figure: { beats: "1/4", label: "semicorchea" },
    });
    expect(facts[1]?.text).toContain("leídas como semicorchea");
    expect(facts[2]?.text).toContain("frente al 15\u00a0%");
    for (const fact of facts) expect(fact.text).not.toMatch(/\d+\/\d+/);
  });

  it("no saca conclusiones de grupos de menos de 200 notas", () => {
    const facts = findings(
      values({
        by_duration: [rate("readdur:1/4", "semicorchea", 150, 120)],
        by_clef: [rate("clef:C3", "clave de do en 3.ª", 120, 60)],
        // 35 notas contra la armadura: un porcentaje de tan pocas no sale como titular.
        by_vs_key: [
          rate("vs:against_key", "contra la armadura", 35, 20),
          rate("vs:in_key", "según la armadura", 900, 90),
        ],
      }),
    );

    expect(facts.map((f) => f.kicker)).toEqual(["Qué se corrige", "Sin errores"]);
    expect(facts[1]?.big).toBe("25\u00a0%");
  });

  it("enseña solo los grupos publicados y avisa si Cadenza aún no lo está", () => {
    const data = payload([group("cadenza", UNPUBLISHED), group("primus")]);

    expect(shownGroups(data).map((g) => g.id)).toEqual(["primus"]);
    expect(cadenzaPending(data)).toBe(true);
    expect(cadenzaPending(payload([group("cadenza"), group("primus")]))).toBe(false);
  });

  it("nombra cada grupo y cada paso de altura en palabras", () => {
    expect(groupInfo("camera_primus").name).toBe("Camera-PrIMuS");
    expect(groupInfo("otro").name).toBe("otro");
    expect(stepName(0)).toContain("solo cambió la alteración");
    expect(stepName(-7)).toBe("7 líneas o espacios más abajo (una octava)");
    expect(stepName(1)).toBe("1 línea o espacio más arriba");
    expect(stepName(8)).toBe("8 o más líneas o espacios más arriba");
    expect(pct(1, 3)).toBe("33,3\u00a0%");
    expect(pct(1, 5000)).toBe("< 0,1\u00a0%");
    expect(pct(1, 0)).toBe("—");
  });

  it("ordena la matriz de figuras de la más corta a la más larga", () => {
    const matrix = durationMatrix(values().durations);

    expect(matrix.reads).toEqual(["1/2", "3/4", "1"]);
    expect(matrix.fixes).toEqual(["1/2", "1"]);
    expect(matrix.count("1/2", "1")).toBe(40);
    expect(matrix.count("1", "1")).toBe(0);
    expect(matrix.max).toBe(40);
    expect(beatsValue("3/4")).toBe(0.75);
    expect(cellAlpha(40, 40)).toBeCloseTo(1);
    expect(cellAlpha(1, 40)).toBeGreaterThan(0.12);
    // Ninguna celda entre 0,78 y 0,9: ni la tinta ni el papel llegarían a 4,5:1.
    for (let n = 1; n <= 400; n++) {
      const alpha = cellAlpha(n, 400);
      expect(alpha <= 0.78 || alpha >= 0.9).toBe(true);
    }
  });
});

describe("el historial y sus páginas", () => {
  it("ofrece las páginas de los extremos y las vecinas, con huecos", () => {
    expect(pageList(0, 3)).toEqual([0, 1, 2]);
    expect(pageList(0, 10)).toEqual([0, 1, null, 8, 9]);
    expect(pageList(4, 10)).toEqual([0, 1, 2, 3, 4, 5, null, 8, 9]);
    expect(pageList(5, 12)).toEqual([0, 1, null, 4, 5, 6, null, 10, 11]);
    // Un hueco de una sola página la enseña a ella.
    expect(pageList(3, 10)).toEqual([0, 1, 2, 3, 4, null, 8, 9]);
  });

  it("busca sin acentos y ordena como el informe", () => {
    expect(fold("Sesión ÁRBOL")).toBe("sesion arbol");
    const rows = [
      { id: "a", label: "a10", read: 20, fixes: 2 },
      { id: "b", label: "a9", read: 2, fixes: 2 },
      { id: "c", label: "b1", read: 30, fixes: 0 },
      { id: "d", label: "B2", read: 10, fixes: 5 },
    ];
    expect(historyRows(rows, "", "rate").map((r) => r.id)).toEqual(["d", "a", "c", "b"]);
    expect(historyRows(rows, "", "fixes").map((r) => r.id)).toEqual(["d", "b", "a", "c"]);
    expect(historyRows(rows, "", "clean").map((r) => r.id)).toEqual(["c", "a", "b", "d"]);
    expect(historyRows(rows, "", "name").map((r) => r.label)).toEqual(["a9", "a10", "b1", "B2"]);
    expect(historyRows(rows, " b ", "name").map((r) => r.id)).toEqual(["b", "c", "d"]);
  });
});
