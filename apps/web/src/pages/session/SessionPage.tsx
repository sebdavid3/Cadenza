import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api/instance";
import { ApiError, errorMessage } from "../../api/errors";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import type { FindingRead } from "../../types";
import { instrumentsSummary, nonBlank, sessionName } from "../transcription/scoreData";
import { listUsers, statusLabel } from "../transcription/sessions";
import { DownloadButton, MidiDownloadButton } from "./DownloadButton";
import { DeskDivider } from "./DeskDivider";
import { clampShare, SHARE_DEFAULT } from "./deskShare";
import { EditBar, type ToolTab } from "./EditBar";
import { useEditor, type Editor } from "./editor";
import { useEffortMeter } from "./effort";
import {
  carryAnchor,
  drawnDuration,
  eventAt,
  figureOf,
  planCommand,
  type EditCommand,
  type EditTarget,
  type PlannedCommand,
} from "./edits";
import type { WriteRequest, WritingMode } from "./writing";
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
import { useLifecycle } from "./lifecycle";
import { LifecyclePanel } from "./LifecyclePanel";
import { useSessionMetadata } from "./metadata";
import { buildPlayback, measureSlots } from "./playback";
import { PlaybackBar } from "./PlaybackBar";
import { usePlayer } from "./player";
import { ScanFigure } from "./ScanFigure";
import { ScoreDataPanel } from "./ScoreDataPanel";
import { ScoreView, type ScoreSnapshot } from "./ScoreView";
import { useSelectionStore } from "./selection";
import {
  sessionDetailQuery,
  sessionFindingsQuery,
  sessionFullImageQuery,
  sessionMidiQuery,
  sessionMusicXmlQuery,
  sessionTimingQuery,
  validatedSeqQuery,
} from "./session";
import { suggestionsAt } from "./suggestions";
import type { SuggestionActions } from "./SuggestionList";
import "./session.css";
import { readStored, writeStored } from "./storage";

/** La figura con que empieza el modo «Escribir» sin nota elegida: la negra (#350). */
const QUARTER = 4;

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
 * En una sesión no asistida el validador no se ejecuta y la vista no habla de él (ADR-0040
 * §13.2). Cada sesión monta su propia vista, para que la selección no pase de una a otra.
 */
export function SessionPage() {
  const { sessionId = "" } = useParams();
  return <SessionView key={sessionId} sessionId={sessionId} />;
}

function SessionView({ sessionId }: { sessionId: string }) {
  const shortId = sessionId.slice(0, 8);
  const user = useAuthStore((state) => state.user);
  const isResearcher = user?.role === "investigador";
  const queryClient = useQueryClient();

  const detail = useQuery(sessionDetailQuery(api, sessionId));
  // El nombre, el compositor y los instrumentos (#240, ADR-0045): lo último que se guardó desde
  // aquí o, si no, lo que trae el detalle.
  const metadataEditor = useSessionMetadata(api, sessionId);
  const metadata = metadataEditor.saved ?? detail.data;
  const name = sessionName({
    session_id: sessionId,
    title: metadata?.title,
    source_filename: metadata?.source_filename,
  });
  const fallbackName = sessionName({
    session_id: sessionId,
    source_filename: metadata?.source_filename,
  });
  const instruments = instrumentsSummary(metadata?.instruments);
  useDocumentTitle(name);
  const seq = detail.data?.current_seq ?? 0;
  const ready = detail.isSuccess;
  // En la condición no asistida no corren ni las reglas ni la capa, y quien corrige no ve nada
  // que venga de ellas: ni el panel, ni las marcas, ni «Revalidar», ni avisos sobre la validación
  // (ADR-0040 §13.2). Hasta saber la condición, tampoco.
  const assisted = detail.data !== undefined && detail.data.condition !== "unassisted";
  const findings = useQuery({
    ...sessionFindingsQuery(api, sessionId, seq),
    enabled: ready && assisted,
  });
  const musicXml = useQuery({ ...sessionMusicXmlQuery(api, sessionId, seq), enabled: ready });
  const image = useQuery({ ...sessionFullImageQuery(api, sessionId), enabled: ready });
  const timing = useQuery({ ...sessionTimingQuery(api, sessionId, seq), enabled: ready });
  // La última validación que se sabe hecha desde esta pestaña (ADR-0035).
  const knownValidated = useQuery(validatedSeqQuery(sessionId)).data ?? null;

  const ownerId = detail.data?.owner_id ?? null;
  const foreign = isResearcher && ownerId !== null && ownerId !== user.id;
  const finalized = detail.data?.status === "finalized";
  // Solo edita, finaliza y reabre quien la transcribió; a un investigador, una sesión ajena le
  // responde 403 (ADR-0012).
  const owned = user !== null && ownerId === user.id;
  const editable = owned && !finalized;
  const users = useQuery({
    queryKey: ["users"],
    queryFn: ({ signal }) => listUsers(api, signal),
    enabled: foreign,
    staleTime: 5 * 60_000,
  });

  const score = detail.data?.current_score ?? null;
  const { active, dismissed } = useMemo(() => splitFindings(findings.data ?? []), [findings.data]);
  const { marks, unplaced } = useMemo(
    () => (score && assisted ? measureMarks(score, active) : { marks: [], unplaced: [] }),
    [score, assisted, active],
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
  // Lo que suena: el mapa de tiempos con las alturas del mismo estado (ADR-0026), cada parte con
  // su instrumento (ADR-0046).
  const partInstruments = detail.data?.instruments;
  const playback = useMemo(
    () => (score && timing.data ? buildPlayback(score, timing.data, partInstruments) : null),
    [score, timing.data, partInstruments],
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
  // El esfuerzo de la corrección (#188, ADR-0050): se mide a quien la transcribió mientras la
  // sesión está abierta, y no se muestra.
  const effort = useEffortMeter(api, sessionId, ready && editable);
  const lifecycle = useLifecycle(api, sessionId, {
    seq,
    assisted,
    reload: () => editorRef.current?.reload() ?? Promise.resolve(null),
    effort,
  });
  // Mientras se revalida o se finaliza, las correcciones esperan: cambiarían el estado validado
  // (ADR-0035, ADR-0043).
  const editor = useEditor(
    api,
    sessionId,
    detail.data,
    // Mientras se guardan los datos de la partitura, también: la respuesta de una corrección
    // traería el MusicXML con los datos de antes (ADR-0045 §3).
    findingActions.revalidating || lifecycle.finalizing || metadataEditor.saving,
    (saved) => {
      effort.saved(saved);
    },
  );
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
  const labelOf = (finding: FindingRead) => findingLabel(score, finding, multiStaff);
  // Aplicar y rechazar una sugerencia (#258): aplicar es una corrección del editor; rechazar, una
  // orden sobre los posibles errores, como descartar.
  const suggestionActions: SuggestionActions | undefined = editable
    ? {
        applyBlocked: editor.blocked || findingActions.busy || lifecycle.busy,
        rejectBlocked:
          findingActions.busy ||
          lifecycle.busy ||
          editor.status.kind === "saving" ||
          editor.status.kind === "reloading" ||
          editor.queued,
        onApply: (finding, suggestion) => void editor.applySuggestion(finding, suggestion),
        onReject: (finding, suggestion) => void findingActions.reject(finding, suggestion),
      }
    : undefined;
  /** Las sugerencias de la nota elegida en el estado que se ve (#258). */
  const noteSuggestions = (target: EditTarget | null) =>
    assisted && target
      ? suggestionsAt(active, target.anchor, detail.data, editor.staleSuggestions)
      : [];
  // Sin controles, la barra sigue si tiene algo que decir (un 409 que dejó la sesión cerrada).
  const showEditor = editable || editor.status.kind !== "idle";
  // El control que tenía el foco en la barra cuando esta pasa de un sitio a otro (ADR-0034).
  const editorFocusRef = useRef<string | null>(null);
  // La mesa de corrección (#341): lo que el navegador recuerda de ella, la pestaña de la barra y si
  // se ven las leyendas de teclas.
  const scanId = useId();
  const scoreId = useId();
  const asideId = useId();
  const [share, setShare] = useState(() =>
    clampShare(Number(readStored("imagen") ?? SHARE_DEFAULT)),
  );
  // Sin preferencia guardada, el panel empieza plegado en una mesa estrecha, donde la partitura
  // necesita el ancho, y abierto en las demás.
  const [asideOpen, setAsideOpen] = useState(() => {
    const stored = readStored("panel");
    if (stored !== null) return stored !== "plegado";
    return !(
      "matchMedia" in window &&
      window.matchMedia("(min-width: 960px) and (max-width: 1599.98px)").matches
    );
  });
  const [tab, setTab] = useState<ToolTab>("note");
  const [keysShown, setKeysShown] = useState(false);
  const toggleKeys = useCallback(() => {
    setKeysShown((shown) => !shown);
  }, []);
  // El modo «Escribir» (#350): la figura con que se escribe, o null fuera de él. Empieza con la
  // de la nota elegida o, sin ninguna, con una negra; abre la pestaña «Nota», la de las figuras.
  const [writing, setWriting] = useState<{ figure: number; dotted: boolean } | null>(null);
  const toggleWriting = () => {
    if (writing) {
      setWriting(null);
      return;
    }
    const { selection } = useSelectionStore.getState();
    const at =
      selection?.sessionId === sessionId && selection.seq === seq ? selection.anchor : null;
    const found = at && score ? eventAt(score, at) : null;
    const current = at && found ? figureOf(drawnDuration({ anchor: at, ...found }, score)) : null;
    setWriting({ figure: current?.figure ?? QUARTER, dotted: current?.dotted ?? false });
    setTab("note");
  };
  // Con la sesión finalizada no hay nada que escribir: el modo «Escribir» no vale.
  const writingOn = editable ? writing : null;
  // Las órdenes de la barra y del teclado: entrar o salir del modo «Escribir» y, en él, la figura
  // y el puntillo eligen con qué se escribe; lo demás va al editor.
  const runCommand = (command: EditCommand, target: EditTarget | null) => {
    if (command.kind === "writing") {
      toggleWriting();
      return;
    }
    if (writingOn && command.kind === "figure") {
      setWriting({ ...writingOn, figure: command.figure });
      return;
    }
    if (writingOn && command.kind === "dot") {
      setWriting({ ...writingOn, dotted: !writingOn.dotted });
      return;
    }
    editor.run(command, target);
  };
  /**
   * Un clic en el modo «Escribir»: insertar una nota nueva, añadir la altura al acorde o dar al
   * evento la altura y la figura del fantasma, que pueden ser dos ediciones (la segunda espera su
   * turno, ADR-0038). Lo que ya es así no se envía; si algo no se puede, el editor dice por qué.
   */
  const write = (request: WriteRequest) => {
    if (!writingOn) return;
    const { target, pitch } = request;
    if (request.kind === "insert") {
      // Elegido el evento ante el que se inserta, la nota nueva queda elegida al guardarse.
      select({ sessionId, seq, anchor: target.anchor });
      editor.run(
        {
          kind: "write-insert",
          pitch,
          figure: writingOn.figure,
          dotted: writingOn.dotted,
          end: request.end,
        },
        target,
      );
      return;
    }
    select({ sessionId, seq, anchor: target.anchor });
    if (request.chord) {
      editor.run({ kind: "write-chord", pitch }, target);
      return;
    }
    const height: PlannedCommand = { kind: "write", pitch };
    const figure: PlannedCommand = {
      kind: "write-figure",
      figure: writingOn.figure,
      dotted: writingOn.dotted,
    };
    const heightPlan = planCommand(height, target, score);
    const figurePlan = planCommand(figure, target, score);
    if (heightPlan.kind === "refused" && heightPlan.reason !== "same") {
      // Lo dice el editor (fuera del registro, una nota que se uniría a un acorde…).
      editor.run(height, target);
      return;
    }
    // Un silencio o un hueco cambia antes de figura: la nota en su lugar toma la suya, y un
    // silencio importado con una figura que las ediciones no admiten no la rechazaría.
    const order = target.event.kind === "rest" ? [figure, height] : [height, figure];
    for (const command of order) {
      const plan = command === height ? heightPlan : figurePlan;
      if (plan.kind === "edit") editor.run(command, target);
    }
  };
  // Esc sale del modo «Escribir» también con el foco fuera de la partitura (tras pulsar
  // «Escribir» o una figura), salvo en un campo o un diálogo, que la usan para lo suyo.
  const writingActive = writingOn !== null;
  useEffect(() => {
    if (!writingActive) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const from = event.target instanceof Element ? event.target : null;
      if (from?.closest("input, select, textarea, [role='dialog'], [aria-modal='true']")) return;
      setWriting(null);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [writingActive]);
  const writingMode: WritingMode | null = writingOn
    ? {
        ...writingOn,
        wait:
          editor.status.kind === "saving" || editor.status.kind === "reloading" || editor.queued
            ? "saving"
            : editor.blocked
              ? "blocked"
              : null,
        onWrite: write,
        onExit: () => {
          setWriting(null);
        },
      }
    : null;

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

  // Solo de lectura, la cabecera dice por qué; corrigiendo, lo dicen la selección y la barra.
  const lead = editable
    ? `Corrige lo que no coincida con la imagen: elige una nota en la partitura y usa la barra de corrección.${
        assisted ? " Los compases en violeta son posibles errores que conviene revisar." : ""
      }`
    : `${
        foreign
          ? "Solo lectura: es una sesión de otra persona y solo ella puede corregirla."
          : finalized
            ? owned
              ? "Sesión finalizada: solo lectura. Si se te pasó algo, reábrela para seguir corrigiendo."
              : "Sesión finalizada: solo lectura."
            : "Solo lectura."
      } Compara la imagen original con la transcripción de HOMR${
        assisted
          ? "; los compases tramados en violeta son posibles errores que conviene revisar."
          : "."
      }`;
  // El panel lateral plegado se queda en un raíl con su nombre; en la condición no asistida no
  // dice nada del validador (ADR-0040 §13.2).
  const findingsTotal = active.length;
  const railLabel = assisted
    ? findings.isSuccess
      ? `Posibles errores · ${String(findingsTotal)}`
      : "Posibles errores"
    : "Historial";

  return (
    <main className="session session--desk" aria-busy={detail.isPending}>
      <header className="session__head">
        <div className="session__titling">
          <BackLink />
          <h1 className="session__title">
            {(nonBlank(metadata?.title) ?? nonBlank(metadata?.source_filename)) ? (
              name
            ) : (
              <>
                Sesión <span className="session__id">{shortId}</span>
              </>
            )}
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
              {metadata?.composer && (
                <div>
                  <dt className="label">Compositor</dt>
                  <dd>{metadata.composer}</dd>
                </div>
              )}
              {instruments && (
                <div>
                  <dt className="label">Instrumentos</dt>
                  <dd>{instruments}</dd>
                </div>
              )}
              {nonBlank(metadata?.title) && metadata?.source_filename && (
                <div>
                  <dt className="label">Archivo</dt>
                  <dd>{metadata.source_filename}</dd>
                </div>
              )}
              {foreign && (
                <div>
                  <dt className="label">Propietario</dt>
                  <dd>{ownerName}</dd>
                </div>
              )}
            </dl>
          )}
          <p className="session__lead">{lead}</p>
        </div>
        <div className="session__actions">
          {owned && detail.data && metadata && (
            <ScoreDataPanel
              metadata={metadata}
              staves={(score?.parts ?? []).map((part) => part.staves.length)}
              fallbackName={fallbackName}
              saving={metadataEditor.saving}
              waiting={
                editor.status.kind === "saving" ||
                editor.status.kind === "reloading" ||
                editor.queued ||
                findingActions.busy ||
                lifecycle.busy
              }
              message={metadataEditor.message}
              onSave={metadataEditor.save}
              onDismissMessage={metadataEditor.clearMessage}
            />
          )}
          <div className="session__downloads">
            <DownloadButton
              sessionId={sessionId}
              xml={musicXml.data}
              status={
                musicXml.data !== undefined ? "ready" : musicXml.isError ? "error" : "loading"
              }
              onRetry={async () => (await musicXml.refetch()).data}
            />
            <MidiDownloadButton
              sessionId={sessionId}
              seq={seq}
              ready={ready}
              fetchMidi={() => queryClient.query(sessionMidiQuery(api, sessionId, seq))}
            />
          </div>
          {owned && detail.data && (
            <LifecyclePanel
              finalized={finalized}
              assisted={assisted}
              busy={lifecycle.busy}
              waiting={
                editor.status.kind === "saving" ||
                editor.status.kind === "reloading" ||
                editor.queued ||
                findingActions.busy
              }
              message={lifecycle.message}
              onFinalize={lifecycle.finalize}
              onReopen={lifecycle.reopen}
            />
          )}
        </div>
      </header>

      <div className="session__body" data-aside={asideOpen ? "open" : "closed"}>
        {/* La mesa de corrección (#341): la imagen original y la partitura lado a lado, con un
            divisor que reparte el ancho; en una columna, la imagen arriba. */}
        <div
          className="session__sheets"
          style={
            {
              "--scan-fr": `${String(Math.round(share * 100))}fr`,
              "--score-fr": `${String(Math.round((1 - share) * 100))}fr`,
            } as CSSProperties
          }
        >
          <a className="session__skip" href={`#${scoreId}`}>
            Ir a la partitura
          </a>
          <ScanFigure
            id={scanId}
            blob={image.data ?? null}
            status={image.isError ? "error" : image.data ? "ready" : "loading"}
          />
          <DeskDivider
            share={share}
            onShare={setShare}
            onCommit={(value) => {
              writeStored("imagen", String(value));
            }}
            controls={scanId}
          />
          <section
            className="sheet sheet--notation"
            id={scoreId}
            tabIndex={-1}
            aria-label="Transcripción"
          >
            {snapshot ? (
              <ScoreView
                snapshot={snapshot}
                sessionId={sessionId}
                marks={marks}
                expectedMeasures={expected}
                selectedKey={selectedKey}
                onPlacement={setPlaced}
                findingsListed={assisted}
                playing={playing}
                onCommand={editable ? runCommand : undefined}
                writing={writingMode}
                editKeysId={editable ? editKeysId : undefined}
                keysHidden={editable && !keysShown}
                editor={
                  showEditor
                    ? (target, { available, focusScore, selectionKeysId }) => (
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
                          tab={tab}
                          onTab={setTab}
                          keysShown={keysShown}
                          onToggleKeys={toggleKeys}
                          selectionKeysId={selectionKeysId}
                          onCommand={runCommand}
                          writing={writingOn}
                          onToggleWriting={toggleWriting}
                          suggestions={{
                            items: noteSuggestions(target),
                            labelOf,
                            actions: suggestionActions,
                          }}
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
                    tab={tab}
                    onTab={setTab}
                    keysShown={keysShown}
                    onToggleKeys={toggleKeys}
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
          </section>
        </div>

        <aside
          className="session__aside"
          aria-label={assisted ? "Posibles errores e historial" : "Historial"}
        >
          <button
            type="button"
            className="aside-toggle"
            aria-expanded={asideOpen}
            aria-controls={asideId}
            aria-label={asideOpen ? "Plegar el panel" : `Desplegar el panel: ${railLabel}`}
            onClick={() => {
              const next = !asideOpen;
              setAsideOpen(next);
              writeStored("panel", next ? "abierto" : "plegado");
            }}
          >
            <PixelIcon name={asideOpen ? "arrow-right" : "arrow-left"} />
            <span className="aside-toggle__text">{asideOpen ? "Plegar" : railLabel}</span>
          </button>
          <div className="session__aside-body" id={asideId} hidden={!asideOpen}>
            {assisted && (
              <FindingsPanel
                marks={marks}
                unplaced={unplaced}
                dismissed={dismissed}
                validation={validation}
                edits={edits}
                seq={seq}
                staleSuggestions={editor.staleSuggestions}
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
                        busy: findingActions.busy || lifecycle.busy,
                        editorBusy:
                          editor.status.kind === "saving" ||
                          editor.status.kind === "reloading" ||
                          editor.queued,
                        pendingId: findingActions.pendingId,
                        onDismiss: findingActions.dismiss,
                        onRestore: findingActions.restore,
                        onRevalidate: findingActions.revalidate,
                        onReload: editor.reload,
                        applyBlocked: editor.blocked || lifecycle.busy,
                        onApply: editor.applySuggestion,
                        onReject: findingActions.reject,
                      }
                    : undefined
                }
              />
            )}
            {detail.data && (
              <HistoryPanel
                edits={detail.data.edits}
                score={detail.data.current_score ?? null}
                multiStaff={multiStaff}
              />
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
