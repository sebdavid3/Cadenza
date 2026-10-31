import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api/instance";
import { ApiError, errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { FindingRead } from "../../types";
import { listUsers, statusLabel } from "../transcription/sessions";
import { DownloadButton } from "./DownloadButton";
import { EditBar } from "./EditBar";
import { useEditor, type Editor } from "./editor";
import { carryAnchor } from "./edits";
import { useFindingActions } from "./findingActions";
import {
  findingLabel,
  findingPlace,
  measureMarks,
  measuresPerStaff,
  splitFindings,
  validationState,
} from "./findings";
import { FindingsPanel } from "./FindingsPanel";
import { historyKey, isTextField } from "./history";
import { HistoryPanel } from "./HistoryPanel";
import { buildPlayback, measureSlots } from "./playback";
import { PlaybackBar } from "./PlaybackBar";
import { usePlayer } from "./player";
import { ScanFigure } from "./ScanFigure";
import { ScoreView, type ScoreSnapshot } from "./ScoreView";
import { useSelectionStore } from "./selection";
import {
  sessionDetailQuery,
  sessionFindingsQuery,
  sessionFullImageQuery,
  sessionMusicXmlQuery,
  sessionTimingQuery,
  validatedSeqQuery,
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
 * Vista de una sesión: la imagen original sobre la partitura transcrita y los posibles errores
 * que señala el validador, marcados por compás (ADR-0021). Quien la transcribió corrige la nota
 * elegida mientras la sesión no esté finalizada (ADR-0030); para los demás es de solo lectura.
 * Cada sesión monta su propia vista, para que la selección no pase de una a otra.
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
  const timing = useQuery({ ...sessionTimingQuery(api, sessionId, seq), enabled: ready });
  // La última validación que se sabe hecha desde esta pestaña (ADR-0035).
  const knownValidated = useQuery(validatedSeqQuery(sessionId)).data ?? null;

  const ownerId = detail.data?.owner_id ?? null;
  const foreign = isResearcher && ownerId !== null && ownerId !== user.id;
  const finalized = detail.data?.status === "finalized";
  // Solo edita quien la transcribió; a un investigador, una sesión ajena le responde 403 (ADR-0012).
  const editable = user !== null && ownerId === user.id && !finalized;
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
  const multiStaff = expected.length > 1;
  const validation = useMemo(
    () => validationState(findings.data ?? [], seq, knownValidated),
    [findings.data, seq, knownValidated],
  );
  const placeOf = useCallback(
    (finding: FindingRead) => findingPlace(score, finding, multiStaff),
    [score, multiStaff],
  );
  // Lo que se dibuja es siempre un estado entero: el MusicXML, el `ScoreIR` y el `seq` del mismo.
  const snapshot = useMemo<ScoreSnapshot | null>(
    () =>
      musicXml.data !== undefined && score
        ? { xml: musicXml.data, transcription: score, seq }
        : null,
    [musicXml.data, score, seq],
  );
  // Lo que suena: el mapa de tiempos con las alturas del mismo estado (ADR-0026).
  const playback = useMemo(
    () => (score && timing.data ? buildPlayback(score, timing.data) : null),
    [score, timing.data],
  );
  const player = usePlayer(playback);
  const playing = useMemo(
    () =>
      score && player.measure !== null
        ? { measure: player.measure, slots: measureSlots(score, player.measure) }
        : null,
    [score, player.measure],
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [placed, setPlaced] = useState(true);
  // La nota elegida es de esta sesión: se olvida al salir de ella (ADR-0027).
  const clearSelection = useSelectionStore((state) => state.clear);
  const select = useSelectionStore((state) => state.select);
  useEffect(() => clearSelection, [clearSelection]);
  // Cuando la vista pasa a un estado posterior (una corrección guardada o una recarga), la nota
  // elegida sigue elegida con su ancla en ese estado (ADR-0011 §2); si su evento ya no está, se
  // olvida. Antes de pintar, para que no parpadee. También si se elige sobre el dibujo de un
  // estado anterior mientras llega el nuevo (#276). Solo se suscribe a si la selección va por
  // detrás: cada movimiento de la selección no tiene por qué volver a pintar toda la vista.
  const selectionBehind = useSelectionStore(
    (state) => state.selection?.sessionId === sessionId && state.selection.seq < seq,
  );
  useLayoutEffect(() => {
    const { selection } = useSelectionStore.getState();
    if (!detail.data || selection?.sessionId !== sessionId || selection.seq >= seq) return;
    const anchor = carryAnchor(selection.anchor, selection.seq, detail.data);
    if (anchor) select({ ...selection, seq, anchor });
    else clearSelection();
  }, [detail.data, sessionId, seq, select, clearSelection, selectionBehind]);

  // El editor del último render: lo usan las órdenes que llegan después (el teclado, una
  // revalidación que encuentra el servidor por delante).
  const editorRef = useRef<Editor | null>(null);
  const findingActions = useFindingActions(api, sessionId, {
    seq,
    labelOf: (finding) => findingLabel(score, finding, multiStaff),
    reload: () => editorRef.current?.reload() ?? Promise.resolve(null),
  });
  // Mientras se revalida, las correcciones esperan: cambiarían el estado validado (ADR-0035).
  const editor = useEditor(api, sessionId, detail.data, findingActions.revalidating);
  const editKeysId = useId();
  // Ctrl+Z y los suyos valen en toda la vista mientras se pueda editar y se vean deshacer y
  // rehacer (con la partitura dibujada o sin poder dibujarse, no mientras carga), salvo en un
  // campo de texto, que tiene su propio deshacer (ADR-0034). La escucha lee el editor del último
  // render.
  const undoShown = editable && (snapshot !== null || musicXml.isError);
  useLayoutEffect(() => {
    editorRef.current = editor;
  });
  useEffect(() => {
    if (!undoShown) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const action = historyKey(event);
      if (!action || event.defaultPrevented || isTextField(event.target)) return;
      event.preventDefault();
      // Mantener la tecla pulsada no encadena órdenes: cada una es una edición del log (D38).
      if (event.repeat) return;
      if (action === "undo") editorRef.current?.undo();
      else editorRef.current?.redo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [undoShown]);
  // Sin controles, la barra sigue si tiene algo que decir (un 409 que dejó la sesión cerrada).
  const showEditor = editable || editor.status.kind !== "idle";
  // El control que tenía el foco en la barra cuando esta pasa de un sitio a otro (ADR-0034).
  const editorFocusRef = useRef<string | null>(null);

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
          {editable
            ? "Compara la imagen original con la transcripción de HOMR y corrige lo que no coincida: elige una nota y cambia su altura, su alteración o su figura, inserta o borra notas y silencios, o cambia la clave y la armadura de su compás. Los compases tramados en violeta son posibles errores que conviene revisar."
            : `${
                foreign
                  ? "Solo lectura: es una sesión de otra persona y solo ella puede corregirla."
                  : finalized
                    ? "Sesión finalizada: solo lectura."
                    : "Solo lectura."
              } Compara la imagen original con la transcripción de HOMR; los compases tramados en violeta son posibles errores que conviene revisar.`}
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
                  musicXml.data !== undefined ? "ready" : musicXml.isError ? "error" : "loading"
                }
                onRetry={async () => (await musicXml.refetch()).data}
              />
            </div>
            <div className="sheet__transport">
              <PlaybackBar
                status={player.status}
                measure={player.measure}
                announcement={player.announcement}
                tempo={player.tempo}
                totalBeats={playback ? playback.totalBeats : null}
                measureCount={playback?.measures.length ?? 0}
                silent={playback !== null && playback.notes.length === 0}
                failure={timing.isError ? "timing" : player.loadFailed ? "load" : null}
                onRetry={() => {
                  if (timing.isError) void timing.refetch();
                  else player.retryLoad();
                }}
                onPlay={player.play}
                onPause={player.pause}
                onStop={player.stop}
                onTempo={player.setTempo}
              />
            </div>
            {snapshot ? (
              <ScoreView
                snapshot={snapshot}
                sessionId={sessionId}
                marks={marks}
                expectedMeasures={expected}
                selectedKey={selectedKey}
                onPlacement={setPlaced}
                playing={playing}
                onCommand={editable ? editor.run : undefined}
                editKeysId={editable ? editKeysId : undefined}
                editor={
                  showEditor
                    ? (target, { available, focusScore }) => (
                        <EditBar
                          editor={editor}
                          editable={editable}
                          undoable={editable}
                          target={target}
                          available={available}
                          score={snapshot.transcription}
                          seq={snapshot.seq}
                          multiStaff={multiStaff}
                          keysId={editKeysId}
                          focusScore={focusScore}
                          focusMemoryRef={editorFocusRef}
                        />
                      )
                    : undefined
                }
              />
            ) : musicXml.isError ? (
              <>
                {/* Sin partitura que dibujar, lo que pasó con la última corrección se sigue viendo,
                    y se puede deshacer la edición que dejó la partitura así. */}
                {showEditor && (
                  <EditBar
                    editor={editor}
                    editable={false}
                    undoable={editable}
                    target={null}
                    available={false}
                    score={score}
                    seq={seq}
                    multiStaff={multiStaff}
                    keysId={editKeysId}
                    focusMemoryRef={editorFocusRef}
                  />
                )}
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
              </>
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

        <div className="session__aside">
          <FindingsPanel
            marks={marks}
            unplaced={unplaced}
            dismissed={dismissed}
            validation={validation}
            edits={edits}
            multiStaff={multiStaff}
            selectable={placed && musicXml.isSuccess}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
            status={findings.isError ? "error" : findings.isSuccess ? "ready" : "loading"}
            errorText={findings.isError ? errorMessage(findings.error) : undefined}
            onRetry={() => void findings.refetch()}
            placeOf={placeOf}
            message={findingActions.message}
            actions={
              editable
                ? {
                    busy: findingActions.busy,
                    editorBusy:
                      editor.status.kind === "saving" ||
                      editor.status.kind === "reloading" ||
                      editor.queued,
                    pendingId: findingActions.pendingId,
                    onDismiss: findingActions.dismiss,
                    onRestore: findingActions.restore,
                    onRevalidate: findingActions.revalidate,
                    onReload: editor.reload,
                  }
                : undefined
            }
          />
          {detail.data && (
            <HistoryPanel
              edits={detail.data.edits}
              score={detail.data.current_score ?? null}
              multiStaff={multiStaff}
            />
          )}
        </div>
      </div>
    </main>
  );
}
