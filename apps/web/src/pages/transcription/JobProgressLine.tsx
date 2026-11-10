import type { QueueProgress } from "./format";
import "./job-progress.css";

/**
 * En qué está una transcripción del servidor (#375): el texto y, mientras HOMR lee los
 * pentagramas, una barra con los ya leídos de la lectura en curso. Nada más: sin porcentajes
 * inventados ni barras que avancen solas.
 */
export function JobProgressLine({
  progress,
  className,
}: {
  progress: QueueProgress;
  className?: string;
}) {
  const { read, staffs } = progress;
  return (
    <div className={className ? `job-progress ${className}` : "job-progress"}>
      <p className="job-progress__text">{progress.text}</p>
      {read !== undefined && staffs !== undefined && staffs > 0 && (
        <span className="job-progress__meter" aria-hidden="true">
          <span style={{ width: `${String((100 * read) / staffs)}%` }} />
        </span>
      )}
    </div>
  );
}
