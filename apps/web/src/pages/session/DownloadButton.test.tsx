import { startTransition, useLayoutEffect } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../../test/auth-helpers";
import { DownloadButton } from "./DownloadButton";

const ID = "3e951fef-8a58-489e-abc9-68cfc3cd405b";

/**
 * Vista a la que se pasa: avisa al confirmarse, antes de los efectos pasivos de React. Tarda más
 * que la porción de tiempo del planificador de React (5 ms), como en una máquina cargada: así
 * React deja la limpieza de los efectos pasivos para otra tarea, y lo que se resuelva en este
 * momento corre antes que ella.
 */
function Next({ onCommit }: { onCommit: () => void }) {
  useLayoutEffect(() => {
    const until = performance.now() + 10;
    while (performance.now() < until) {
      // Espera activa: ocupa la porción de tiempo.
    }
    onCommit();
  }, [onCommit]);
  return <p>Otra vista</p>;
}

const act = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
let actEnvironment: boolean | undefined;

beforeEach(() => {
  // Sin el entorno de act, React programa los efectos como en el navegador, no al final de act.
  actEnvironment = act.IS_REACT_ACT_ENVIRONMENT;
  act.IS_REACT_ACT_ENVIRONMENT = false;
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:musicxml");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
});

afterEach(() => {
  act.IS_REACT_ACT_ENVIRONMENT = actEnvironment;
});

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("DownloadButton", () => {
  it("no descarga lo que llega al salir de la vista, antes de que React limpie sus efectos", async () => {
    const names: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      names.push(this.download);
    });
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const retry = deferred<string | undefined>();
    root.render(
      <DownloadButton
        sessionId={ID}
        xml={undefined}
        status="error"
        onRetry={() => retry.promise}
      />,
    );
    while (!host.querySelector("button")) await tick();

    host.querySelector("button")?.click();
    // Se sale con una navegación (una transición, como React Router) y la respuesta llega justo
    // cuando React ya quitó el botón de la página pero aún no ha limpiado sus efectos pasivos.
    startTransition(() => {
      root.render(
        <Next
          onCommit={() => {
            retry.resolve("<score-partwise/>");
          }}
        />,
      );
    });
    while (!host.textContent.includes("Otra vista")) await tick();
    await tick();

    expect(host.querySelector("button")).toBeNull();
    expect(names).toEqual([]);
    root.unmount();
    host.remove();
  });
});
