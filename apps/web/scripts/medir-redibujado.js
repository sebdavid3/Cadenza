/**
 * Mide el redibujado de la partitura tras una edición (#276) en la vista de una sesión editable.
 *
 * Uso: abrir la sesión con la web en desarrollo o en producción, elegir una nota y pegar este
 * archivo en la consola del navegador (o evaluarlo con una herramienta de automatización). Envía
 * `ediciones` correcciones de altura (Mayús + flecha arriba y abajo, alternadas: la partitura vuelve
 * a como estaba), espera a que cada una esté dibujada y con su mapa de notas, y lee las marcas de
 * rendimiento de la vista (`cadenza:orden-N…` de #275 y `cadenza:dibujo:*` de #276).
 *
 * Devuelve, por medida, n, mediana, p95 y máximo en milisegundos:
 * - `orden`: del envío de la orden al estado dibujado (`cadenza:orden-N`);
 * - `servidor`: del envío a la respuesta (`cadenza:orden-N:servidor`);
 * - `respuesta→dibujado`: de la respuesta al estado dibujado;
 * - `leer`, `dibujar`, `mapa`: las etapas del dibujo del estado nuevo;
 * - `orden→mapa`: del envío al final del mapa de notas del estado nuevo.
 *
 * No escribe cifras: si falta la partitura, la nota elegida o alguna marca, falla con un mensaje.
 */
(async (ediciones = 20, esperaMaxima = 30_000) => {
  const app = document.querySelector('[role="application"]');
  if (!app) throw new Error("No hay una partitura con notas que elegir en esta vista.");
  if (!document.querySelector(".notation__selection")) {
    throw new Error("Elige una nota antes de medir.");
  }
  const byName = (name, type) => performance.getEntriesByName(name, type);
  const orders = () =>
    performance
      .getEntriesByType("measure")
      .filter((entry) => /^cadenza:orden-\d+$/.test(entry.name));
  const stage = (name, seq) =>
    performance
      .getEntriesByName(`cadenza:dibujo:${name}`, "measure")
      .filter((entry) => entry.detail?.seq === seq);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const samples = [];
  for (let index = 0; index < ediciones; index += 1) {
    const before = orders().length;
    const started = performance.now();
    app.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: index % 2 === 0 ? "ArrowUp" : "ArrowDown",
        shiftKey: true,
        bubbles: true,
      }),
    );
    let order = null;
    let map = null;
    while (performance.now() - started < esperaMaxima) {
      order = orders()[before] ?? null;
      if (order) {
        const received = byName(`${order.name}:recibir`, "mark")[0];
        const seq = received?.detail?.seq;
        map = seq === undefined ? null : (stage("mapa", seq).at(-1) ?? null);
        if (map) break;
      }
      await sleep(20);
    }
    if (!order || !map) {
      throw new Error(`La edición ${index + 1} no llegó a dibujarse con su mapa de notas.`);
    }
    const received = byName(`${order.name}:recibir`, "mark")[0];
    const sent = byName(`${order.name}:enviar`, "mark")[0];
    const server = byName(`${order.name}:servidor`, "measure")[0];
    const seq = received.detail.seq;
    const read = stage("leer", seq).at(-1);
    const draw = stage("dibujar", seq).at(-1);
    if (!sent || !server || !read || !draw) {
      throw new Error(`Faltan marcas de la edición ${index + 1} (estado ${seq}).`);
    }
    samples.push({
      orden: order.duration,
      servidor: server.duration,
      "respuesta→dibujado": order.duration - server.duration,
      leer: read.duration,
      dibujar: draw.duration,
      mapa: map.duration,
      "orden→mapa": map.startTime + map.duration - sent.startTime,
    });
    // La orden siguiente sale con el editor libre, como la de una persona.
    await sleep(150);
  }

  const quantile = (values, q) => {
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.ceil(q * sorted.length) - 1)];
  };
  const summary = {};
  for (const key of Object.keys(samples[0])) {
    const values = samples.map((sample) => sample[key]);
    summary[key] = {
      n: values.length,
      mediana: Number(quantile(values, 0.5).toFixed(1)),
      p95: Number(quantile(values, 0.95).toFixed(1)),
      max: Number(Math.max(...values).toFixed(1)),
    };
  }
  const svg = document.querySelector(".notation__host svg");
  summary.condiciones = {
    figuras: document.querySelectorAll(".notation__host .vf-stavenote").length,
    altoSvg: svg ? Math.round(svg.getBoundingClientRect().height) : null,
    anchoVentana: window.innerWidth,
    agente: navigator.userAgent,
  };
  console.table(summary);
  return summary;
})();
