import { useEffect, useState } from "react";

import { useEditorStore } from "../store/editorStore";

export function EffortMetrics() {
  const startedAt = useEditorStore((state) => state.startedAt);
  const firstEditAt = useEditorStore((state) => state.firstEditAt);
  const cursor = useEditorStore((state) => state.cursor);
  const interventions = useEditorStore((state) => state.interventions);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const elapsed = startedAt ? Math.round((now - startedAt) / 1000) : 0;
  const toFirstEdit =
    startedAt && firstEditAt ? Math.round((firstEditAt - startedAt) / 1000) : null;

  return (
    <div className="metrics">
      <p>
        Tiempo de sesión: <strong>{elapsed}s</strong>
      </p>
      <p>
        Ediciones aplicadas: <strong>{cursor}</strong>
      </p>
      <p>
        Tiempo hasta 1ª edición:{" "}
        <strong>{toFirstEdit === null ? "—" : `${toFirstEdit}s`}</strong>
      </p>
      <ul>
        {Object.entries(interventions).map(([measure, count]) => (
          <li key={measure}>
            Compás {measure}: {count} intervención(es)
          </li>
        ))}
      </ul>
    </div>
  );
}
