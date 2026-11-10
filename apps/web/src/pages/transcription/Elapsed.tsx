import { useSyncExternalStore } from "react";

function subscribeToClock(onTick: () => void) {
  const timer = setInterval(onTick, 1000);
  return () => {
    clearInterval(timer);
  };
}

/** Segundos desde que empezó la transcripción en curso: progreso visible sin bloquear. */
export function Elapsed({ since }: { since: number }) {
  const seconds = useSyncExternalStore(subscribeToClock, () =>
    Math.max(0, Math.floor((Date.now() - since) / 1000)),
  );
  return (
    <span className="queue__elapsed" aria-hidden="true">
      {seconds} s
    </span>
  );
}
