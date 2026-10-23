import { useEffect, useRef } from "react";
import type { Measure } from "./incipit";
import { drawScan } from "./scan";

/** El incipit como imagen escaneada, pixelada. Decorativo. */
export function IncipitScan({ measures, className }: { measures: Measure[]; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) drawScan(canvas, measures);
  }, [measures]);

  return <canvas className={className} ref={canvasRef} aria-hidden="true" />;
}
