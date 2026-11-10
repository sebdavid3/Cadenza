import type { TranscriptionJobRead } from "../../types";
import type { QueueItem } from "./queue";

/** Tamaño de un archivo en KB o MB, en español. */
export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString("es", { maximumFractionDigits: 1 })} MB`;
}

/** Lo que el validador señaló, en las palabras de la mesa de corrección (#370). */
export function findingsLabel(count: number): string {
  if (count === 0) return "Sin posibles errores";
  return count === 1 ? "1 posible error" : `${String(count)} posibles errores`;
}

export function editsLabel(count: number): string {
  return count === 1 ? "1 edición" : `${String(count)} ediciones`;
}

/** Lo que dice la lámina de una imagen de la cola sobre su transcripción (#375). */
export interface QueueProgress {
  text: string;
  /** Pentagramas ya leídos de `staffs` en la lectura en curso: la barra, solo con lo hecho. */
  read?: number;
  staffs?: number;
}

const SECOND_READING = "Segunda lectura, con el piano por separado";

/**
 * En qué está una transcripción del servidor, en lenguaje llano y solo con lo que dice que ha
 * hecho: en cola y cuántas van delante, detectando los pentagramas, leyendo el pentagrama X de N
 * (y la segunda lectura del piano) o revisando. Null si ya terminó.
 */
export function jobProgress(job: TranscriptionJobRead): QueueProgress | null {
  const piano = job.reading === "piano";
  switch (job.stage) {
    case "queued": {
      const ahead = job.ahead ?? 0;
      return {
        text: ahead === 0 ? "En cola: es la siguiente" : `En cola: ${String(ahead)} por delante`,
      };
    }
    case "detecting":
      return {
        text: piano
          ? `${SECOND_READING}: detectando los pentagramas`
          : "Detectando los pentagramas",
      };
    case "reading": {
      const { staff, staffs } = job;
      if (!staff || !staffs) return { text: piano ? SECOND_READING : "Leyendo los pentagramas" };
      return {
        text: piano
          ? `${SECOND_READING}: pentagrama ${String(staff)} de ${String(staffs)}`
          : `Leyendo el pentagrama ${String(staff)} de ${String(staffs)}`,
        read: staff - 1,
        staffs,
      };
    }
    case "reviewing":
      return { text: "Revisando el compás y los posibles errores" };
    default:
      return null;
  }
}

/** Lo que dice la lámina de una imagen de la cola sobre su transcripción. */
export function queueProgress(item: QueueItem): QueueProgress | null {
  if (item.status === "queued" && !item.job) {
    return item.uploading ? { text: "Subiendo la imagen" } : null;
  }
  if (item.status !== "queued" && item.status !== "transcribing") return null;
  if (!item.job) return null;
  // En la lámina, el rótulo ya dice «En cola».
  if (item.job.stage === "queued") {
    const ahead = item.job.ahead ?? 0;
    return { text: ahead === 0 ? "Es la siguiente" : `${String(ahead)} por delante` };
  }
  return jobProgress(item.job);
}

/** El recuento de la cola: lo pendiente, lo que está en curso, lo transcrito y lo fallido. */
export function queueSummary(items: QueueItem[]): string {
  const count = (status: QueueItem["status"]) =>
    items.filter((item) => item.status === status).length;
  const done = count("done");
  const running = count("transcribing");
  return [
    `${String(count("queued"))} en cola`,
    ...(running > 0 ? [`${String(running)} en curso`] : []),
    `${String(done)} ${done === 1 ? "transcrita" : "transcritas"}`,
    `${String(count("error"))} con error`,
  ].join(" · ");
}
