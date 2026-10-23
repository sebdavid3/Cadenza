import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api/instance";
import { ApiError, errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { listUsers, statusLabel } from "../transcription/sessions";
import { DownloadButton } from "./DownloadButton";
import { measureMarks, measuresPerStaff, splitFindings, staleValidationSeq } from "./findings";
import { FindingsPanel } from "./FindingsPanel";
import { ScanFigure } from "./ScanFigure";
import { ScoreView } from "./ScoreView";
import {
  sessionDetailQuery,
  sessionFindingsQuery,
  sessionFullImageQuery,
  sessionMusicXmlQuery,
} from "./session";
import "./session.css";

function BackLink() {
  return (
    <Link className="label session__back" to="/transcripcion">
      <PixelIcon name="arrow-left" />
      Sesiones
    </Link>
  );
}

/** La sesión no existe o es de otra persona: la API responde igual a las dos (ADR-0012). */
function SessionNotFound() {
  return (
    <main className="session session--missing">
      <BackLink />
      <h1 className="session__title">Sesión no encontrada</h1>
      <p className="session__lead">
        No existe o no tienes acceso a ella. Las sesiones de cada persona solo las ven ella y los
        investigadores.
      </p>
    </main>
  );
}

/**
 * Vista de solo lectura de una sesión: la imagen original sobre la partitura transcrita y los
 * posibles errores que señala el validador, marcados por compás (ADR-0021). No edita nada. Cada
 * sesión monta su propia vista, para que la selección no pase de una a otra.
 */
export function SessionPage() {
  const { sessionId = "" } = useParams();
  return <SessionView key={sessionId} sessionId={sessionId} />;
}

function SessionView({ sessionId }: { sessionId: string }) {
  const shortId = sessionId.slice(0, 8);
  useDocumentTitle(`Sesión ${shortId}`);
  const user = useAuthStore((state) => state.user);
  const isResearcher = user?.role === "investigador";

  const detail = useQuery(sessionDetailQuery(api, sessionId));
  const seq = detail.data?.current_seq ?? 0;
  const ready = detail.isSuccess;
  const findings = useQuery({ ...sessionFindingsQuery(api, sessionId, seq), enabled: ready });
  const musicXml = useQuery({ ...sessionMusicXmlQuery(api, sessionId, seq), enabled: ready });
  const image = useQuery({ ...sessionFullImageQuery(api, sessionId), enabled: ready });

  const ownerId = detail.data?.owner_id ?? null;
  const foreign = isResearcher && ownerId !== null && ownerId !== user.id;
  const users = useQuery({
    queryKey: ["users"],
    queryFn: ({ signal }) => listUsers(api, signal),
    enabled: foreign,
    staleTime: 5 * 60_000,
  });

  const score = detail.data?.current_score ?? null;
  const { active, dismissed } = useMemo(() => splitFindings(findings.data ?? []), [findings.data]);
  const { marks, unplaced } = useMemo(
    () => (score ? measureMarks(score, active) : { marks: [], unplaced: [] }),
    [score, active],
  );
  const expected = useMemo(() => (score ? measuresPerStaff(score) : []), [score]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [placed, setPlaced] = useState(true);

  if (detail.error instanceof ApiError && detail.error.kind === "not-found") {
    return <SessionNotFound />;
  }

  // Sin datos que enseñar; si ya los había, un fallo al recargarlos no tapa la vista.
  if (detail.isError && !detail.data) {
    return (
      <main className="session session--missing">
        <BackLink />
        <h1 className="session__title">No se pudo cargar la sesión</h1>
        <div className="session__error" role="alert">
          <p>{errorMessage(detail.error)}</p>
          <button type="button" className="button" onClick={() => void detail.refetch()}>
            Reintentar
          </button>
        </div>
      </main>
    );
  }

  const ownerName =
    users.data?.find((candidate) => candidate.id === ownerId)?.username ?? ownerId?.slice(0, 8);
  const edits = detail.data?.edits.length ?? 0;

  return (
    <main className="session" aria-busy={detail.isPending}>
      <header className="session__head">
        <BackLink />
        <h1 className="session__title">
          Sesión <span className="session__id">{shortId}</span>
        </h1>
        {detail.data && (
          <dl className="session__meta">
            <div>
              <dt className="label">Estado</dt>
              <dd>{statusLabel(detail.data.status ?? "")}</dd>
            </div>
            <div>
              <dt className="label">Ediciones</dt>
              <dd>{edits}</dd>
            </div>
            {foreign && (
              <div>
                <dt className="label">Propietario</dt>
                <dd>{ownerName}</dd>
              </div>
            )}
          </dl>
        )}
        <p className="session__lead">
          Solo lectura. Compara la imagen original con la transcripción de HOMR; los compases
          tramados en violeta son posibles errores que conviene revisar.
        </p>
      </header>

      <div className="session__body">
        {/* En el DOM, primero la transcripción; en escritorio la imagen se dibuja encima. */}
        <section className="session__sheets" aria-label="Transcripción e imagen original">
          <figure className="sheet sheet--notation">
            <figcaption className="label sheet__caption">Transcripción</figcaption>
            <div className="sheet__bar">
              <DownloadButton
                sessionId={sessionId}
                xml={musicXml.data}
                status={
                  musicXml.data !== undefined
                    ? "ready"
                    : musicXml.isError && !musicXml.isFetching
                      ? "error"
                      : "loading"
                }
                onRetry={async () => (await musicXml.refetch()).data}
              />
            </div>
            {musicXml.data ? (
              <ScoreView
                key={seq}
                xml={musicXml.data}
                marks={marks}
                expectedMeasures={expected}
                selectedKey={selectedKey}
                onPlacement={setPlaced}
              />
            ) : musicXml.isError ? (
              <div className="notation__failed" role="alert">
                <p className="notation__failed-title">No se pudo dibujar la partitura.</p>
                <p>{errorMessage(musicXml.error)}</p>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => void musicXml.refetch()}
                >
                  Reintentar
                </button>
              </div>
            ) : (
              <div className="notation notation--placeholder" aria-hidden="true" />
            )}
          </figure>
          <figure className="sheet sheet--scan">
            <figcaption className="label sheet__caption">Imagen original</figcaption>
            <ScanFigure
              blob={image.data ?? null}
              status={image.isError ? "error" : image.data ? "ready" : "loading"}
            />
          </figure>
        </section>

        <FindingsPanel
          marks={marks}
          unplaced={unplaced}
          dismissed={dismissed}
          staleSeq={staleValidationSeq(findings.data ?? [], seq)}
          edits={edits}
          multiStaff={expected.length > 1}
          selectable={placed && musicXml.isSuccess}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
          status={findings.isError ? "error" : findings.isSuccess ? "ready" : "loading"}
          errorText={findings.isError ? errorMessage(findings.error) : undefined}
          onRetry={() => void findings.refetch()}
        />
      </div>
    </main>
  );
}
