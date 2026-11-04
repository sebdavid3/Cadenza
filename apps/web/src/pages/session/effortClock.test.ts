import { describe, expect, it } from "vitest";
import { EffortClock } from "./effortClock";

const MINUTE = 60_000;

describe("EffortClock (#188, protocolo §3.4)", () => {
  it("suma el tiempo con actividad", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(0);
    clock.activity(30_000);
    clock.activity(90_000);
    expect(clock.read(100_000)).toBe(100_000);
  });

  it("de una pausa larga solo cuenta el umbral", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(0);
    clock.activity(10_000);
    // Diez minutos sin tocar nada: cuentan dos.
    clock.activity(10_000 + 10 * MINUTE);
    expect(clock.read(10_000 + 10 * MINUTE)).toBe(10_000 + 2 * MINUTE);
    // Y se sigue contando desde la nueva actividad.
    expect(clock.read(10_000 + 10 * MINUTE + 5_000)).toBe(10_000 + 2 * MINUTE + 5_000);
  });

  it("una pausa justo del umbral cuenta entera", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(0);
    clock.activity(2 * MINUTE);
    expect(clock.read(2 * MINUTE)).toBe(2 * MINUTE);
  });

  it("leer en medio de una pausa larga no la cuenta dos veces", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(0);
    expect(clock.read(MINUTE)).toBe(MINUTE);
    expect(clock.read(5 * MINUTE)).toBe(2 * MINUTE);
    expect(clock.read(9 * MINUTE)).toBe(2 * MINUTE);
    clock.activity(9 * MINUTE);
    expect(clock.read(9 * MINUTE + 1_000)).toBe(2 * MINUTE + 1_000);
  });

  it("parado no suma, y al volver empieza una pausa nueva", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(0);
    clock.activity(20_000);
    clock.stop(30_000); // la pestaña se oculta
    expect(clock.running).toBe(false);
    clock.activity(40_000); // no cuenta: está parado
    expect(clock.read(10 * MINUTE)).toBe(30_000);
    clock.start(10 * MINUTE); // vuelve a la pestaña
    expect(clock.read(10 * MINUTE + 15_000)).toBe(45_000);
    // Sin tocar nada tras volver: el umbral desde la vuelta.
    expect(clock.read(20 * MINUTE)).toBe(30_000 + 2 * MINUTE);
  });

  it("empezar dos veces no reinicia la pausa", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(0);
    clock.start(5 * MINUTE);
    expect(clock.read(5 * MINUTE)).toBe(2 * MINUTE);
  });

  it("parte del tiempo que ya había (una recarga)", () => {
    const clock = new EffortClock(2 * MINUTE, 42_000);
    expect(clock.read(1_000)).toBe(42_000);
    clock.start(1_000);
    expect(clock.read(2_000)).toBe(43_000);
  });

  it("un instante anterior no resta ni suma", () => {
    const clock = new EffortClock(2 * MINUTE);
    clock.start(10_000);
    expect(clock.read(5_000)).toBe(0);
    clock.activity(5_000);
    expect(clock.read(12_000)).toBe(2_000);
  });
});
