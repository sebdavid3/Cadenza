import { act, fireEvent, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DRAG_IDLE_MS, usePageDrop } from "./usePageDrop";

function png(name: string) {
  return new File([new Uint8Array(8)], name, { type: "image/png" });
}

const files = (list: File[] = []) => ({ dataTransfer: { files: list, types: ["Files"] } });
const text = { dataTransfer: { files: [], types: ["text/plain"] } };

describe("soltar imágenes en cualquier parte de la vista (#370)", () => {
  let a: HTMLElement;
  let b: HTMLElement;

  beforeEach(() => {
    vi.useFakeTimers();
    a = document.body.appendChild(document.createElement("div"));
    b = a.appendChild(document.createElement("div"));
  });

  afterEach(() => {
    vi.useRealTimers();
    a.remove();
  });

  it("cuenta los elementos que cruza: avisa hasta salir del último", () => {
    const { result } = renderHook(() => usePageDrop(vi.fn()));

    fireEvent.dragEnter(a, files());
    fireEvent.dragEnter(b, files());
    fireEvent.dragLeave(a, files());
    expect(result.current).toBe(true);

    fireEvent.dragLeave(b, files());
    expect(result.current).toBe(false);
  });

  it("ignora lo que no son archivos", () => {
    const { result } = renderHook(() => usePageDrop(vi.fn()));

    fireEvent.dragEnter(a, text);
    expect(result.current).toBe(false);
    expect(fireEvent.dragOver(a, text)).toBe(true);
  });

  it("deja de avisar si dejan de llegar dragover, aunque se pierda un dragleave", () => {
    const { result } = renderHook(() => usePageDrop(vi.fn()));

    fireEvent.dragEnter(a, files());
    fireEvent.dragEnter(b, files());
    // b desaparece: su dragleave no llega a la ventana.
    b.remove();
    fireEvent.dragOver(a, files());
    act(() => {
      vi.advanceTimersByTime(DRAG_IDLE_MS - 1);
    });
    expect(result.current).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe(false);
  });

  it("al soltar entrega los archivos, cancela al navegador y deja de avisar", () => {
    const onFiles = vi.fn();
    const { result } = renderHook(() => usePageDrop(onFiles));

    fireEvent.dragEnter(a, files());
    // dragover cancelado: la página acepta lo que se suelte.
    expect(fireEvent.dragOver(a, files())).toBe(false);
    const accepted = fireEvent.drop(a, files([png("uno.png")]));

    expect(accepted).toBe(false);
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "uno.png" })]);
    expect(result.current).toBe(false);
  });
});
