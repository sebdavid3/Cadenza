import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MUSICXML_TYPE, musicXmlFile, REVOKE_DELAY_MS, saveFile } from "./download";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("descarga del MusicXML", () => {
  it("nombra el archivo con los 8 primeros caracteres del id, sin depender de cabeceras", async () => {
    const file = musicXmlFile("3e951fef-8a58-489e-abc9-68cfc3cd405b", "<score-partwise/>");

    expect(file.name).toBe("cadenza-3e951fef.musicxml");
    expect(file.blob.type).toBe(MUSICXML_TYPE);
    expect(MUSICXML_TYPE).toBe("application/vnd.recordare.musicxml+xml");
    expect(await file.blob.text()).toBe("<score-partwise/>");
  });

  it("descarga con un enlace temporal y revoca la URL del Blob después", () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:descarga");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const clicked: { href: string; download: string; attached: boolean }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push({ href: this.href, download: this.download, attached: this.isConnected });
    });
    const blob = new Blob(["<score-partwise/>"], { type: MUSICXML_TYPE });

    saveFile({ name: "cadenza-3e951fef.musicxml", blob });

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clicked).toEqual([
      { href: "blob:descarga", download: "cadenza-3e951fef.musicxml", attached: true },
    ]);
    expect(document.querySelector("a[download]")).toBeNull();
    // Safari empieza la descarga después del clic: la URL se revoca con margen.
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(REVOKE_DELAY_MS);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:descarga");
  });
});
