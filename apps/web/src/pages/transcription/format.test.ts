import { describe, expect, it } from "vitest";
import { job } from "../../test/jobs";
import { jobProgress, jobStageAnnouncement, queueProgress } from "./format";
import type { QueueItem } from "./queue";

describe("el avance de una transcripción, en palabras (#375)", () => {
  const reading = (kind: "first" | "piano", staff: number, staffs: number) =>
    job({ id: "j", stage: "reading", ahead: null, reading: kind, staff, staffs });

  it("solo con lo que el servidor dice que ha hecho: la barra cuenta los ya leídos", () => {
    expect(jobProgress(job({ id: "j", ahead: 3 }))).toEqual({ text: "En cola: 3 por delante" });
    expect(jobProgress(job({ id: "j", ahead: 0 }))).toEqual({ text: "En cola: es la siguiente" });
    expect(jobProgress(job({ id: "j", stage: "detecting", ahead: null }))).toEqual({
      text: "Preparando la lectura",
    });
    expect(jobProgress(job({ id: "j", stage: "detecting", reading: "first" }))).toEqual({
      text: "Detectando los pentagramas",
    });
    expect(jobProgress(reading("first", 1, 4))).toEqual({
      text: "Leyendo el pentagrama 1 de 4",
      read: 0,
      staffs: 4,
    });
    expect(jobProgress(reading("piano", 6, 6))).toEqual({
      text: "Segunda lectura, con el piano por separado: pentagrama 6 de 6",
      read: 5,
      staffs: 6,
    });
    expect(jobProgress(job({ id: "j", stage: "reviewing" }))?.text).toBe(
      "Revisando el compás y los posibles errores",
    );
    expect(jobProgress(job({ id: "j", stage: "done" }))).toBeNull();
  });

  it("en la lámina, el rótulo ya dice «En cola»; subiendo, sin trabajo todavía", () => {
    const item = (changes: Partial<QueueItem>): QueueItem => ({
      id: "a",
      name: "a.png",
      status: "queued",
      ...changes,
    });
    expect(queueProgress(item({ uploading: true }))).toEqual({ text: "Subiendo la imagen" });
    expect(queueProgress(item({}))).toBeNull();
    expect(queueProgress(item({ job: job({ id: "j", ahead: 2 }) }))).toEqual({
      text: "2 por delante",
    });
    expect(queueProgress(item({ status: "error", job: job({ id: "j", stage: "failed" }) }))).toBe(
      null,
    );
  });

  it("al lector de pantalla, la etapa sin el número de pentagrama", () => {
    expect(jobStageAnnouncement(undefined)).toBe("Subiendo la imagen");
    expect(jobStageAnnouncement(reading("first", 3, 8))).toBe("Leyendo los pentagramas");
    expect(jobStageAnnouncement(reading("piano", 1, 6))).toBe(
      "Segunda lectura, con el piano por separado",
    );
    expect(jobStageAnnouncement(job({ id: "j", stage: "detecting" }))).toBe(
      "Preparando la lectura",
    );
  });
});
