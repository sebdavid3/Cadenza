import { useEffect, useRef, useState } from "react";
import type { DrawnBarRead, FigureRead } from "../../types";
import { DrawnBar } from "./DrawnBar";
import { engrave, canEngrave, accentColor } from "./engrave";
import { barMusicXml } from "./musicxml";

// El compás de un ejemplo grabado con OSMD, como en el editor (#424): lo que leyó HOMR y lo
// correcto, cada uno en su pentagrama, con la nota del ejemplo en violeta. Si no se puede
// escribir o grabar (o el navegador no sabe medir SVG), se dibuja como en el informe.

export function EngravedBar({
  bar,
  atRead,
  atFix,
  measure,
  figures,
}: {
  bar: DrawnBarRead;
  atRead: number | null | undefined;
  atFix: number | null | undefined;
  measure: string;
  figures: Record<string, FigureRead>;
}) {
  const readHost = useRef<HTMLDivElement>(null);
  const fixedHost = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const color = accentColor();
  const readXml = barMusicXml(bar.clef, bar.key, bar.read, atRead, figures, color);
  const fixedXml = barMusicXml(bar.clef, bar.key, bar.fixed, atFix, figures, color);
  const engraved = canEngrave() && readXml !== null && fixedXml !== null && !failed;

  useEffect(() => {
    if (!engraved || !readHost.current || !fixedHost.current) return;
    const controller = new AbortController();
    Promise.all([
      engrave(readHost.current, readXml, controller.signal),
      engrave(fixedHost.current, fixedXml, controller.signal),
    ]).catch(() => {
      if (!controller.signal.aborted) setFailed(true);
    });
    return () => {
      controller.abort();
    };
  }, [engraved, readXml, fixedXml]);

  if (!engraved) {
    return <DrawnBar bar={bar} atRead={atRead} atFix={atFix} measure={measure} figures={figures} />;
  }
  return (
    <div
      className="homr__engraved"
      role="img"
      aria-label={`Compás ${measure}: lo que leyó HOMR y lo correcto`}
    >
      <span className="homr__engraved-tag" aria-hidden="true">
        HOMR leyó
      </span>
      <div className="homr__engraved-staff" ref={readHost} />
      <span className="homr__engraved-tag" aria-hidden="true">
        Correcto
      </span>
      <div className="homr__engraved-staff" ref={fixedHost} />
    </div>
  );
}
