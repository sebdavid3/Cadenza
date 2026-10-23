import { useEffect, useRef } from "react";
import { whenFontsReady } from "../../styles/whenFontsReady";
import type { Measure } from "./incipit";
import { drawScan } from "./scan";

/** El incipit como imagen escaneada, pixelada. Decorativo. */
export function IncipitScan({ measures, className }: { measures: Measure[]; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let cancelled = false;
    void whenFontsReady().then(() => {
      if (!cancelled) drawScan(canvas, measures);
    });
    return () => {
      cancelled = true;
    };
  }, [measures]);

  return <canvas className={className} ref={canvasRef} aria-hidden="true" />;
}
