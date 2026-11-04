import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode, type Ref } from "react";
import { Link } from "react-router";
import { errorMessage } from "../../api/errors";
import { api } from "../../api/instance";
import "../../components/button.css";
import { PixelIcon } from "../../components/PixelIcon";
import type {
  PartInstrumentRead,
  PreviewResponse,
  ScoreIRPayload,
  TimingMapRead,
} from "../../types";
import { measuresPerStaff } from "../session/findings";
import { buildPlayback, measureSlots } from "../session/playback";
import { PlaybackBar } from "../session/PlaybackBar";
import { usePlayer } from "../session/player";
import { ScoreView, type ScoreSnapshot } from "../session/ScoreView";
import { sessionDetailQuery, sessionMusicXmlQuery, sessionTimingQuery } from "../session/session";
import "../session/session.css";
import { nonBlank, sessionName } from "../transcription/scoreData";
import "../transcription/transcription.css";

/** Lo que se enseña de una transcripción en la portada, venga de donde venga. */
export interface ResultData {
  /** Clave de la vista de la partitura: la sesión (o la transcripción) a la que pertenece. */
  viewKey: string;
  name: string;
  /** Posibles errores que señalan las reglas; null si no se habla de ellos (ADR-0040 §13.2). */
  findingsCount: number | null;
  score: ScoreIRPayload | null;
  xml: string | null;
  seq: number;
  timing: TimingMapRead | null;
  instruments?: PartInstrumentRead[];
  /** Fallo al traer lo que se enseña, y cómo reintentarlo (sin reintento si no hay nada que pedir). */
  failure: string | null;
  onRetry?: () => void;
  /** Si el audio no se pudo preparar por falta del mapa de tiempos. */
  timingFailed: boolean;
}

function findingsText(count: number): string {
  if (count === 0) return "Sin posibles errores señalados";
  return count === 1 ? "1 posible error" : `${String(count)} posibles errores`;
}

interface ResultViewProps {
  data: ResultData;
  headingRef?: Ref<HTMLHeadingElement>;
  /** «Editar» y lo que proceda: cada origen sabe adónde lleva. */
  actions: ReactNode;
}

/**
 * Resultado de una transcripción en la portada (#277, ADR-0053): su nombre, cuántos posibles
 * errores señalan las reglas, la reproducción y la partitura en solo lectura. Para corregirla hay
 * que abrirla: aquí no se elige ninguna nota.
 */
export function ResultView({ data, headingRef, actions }: ResultViewProps) {
  const { score, xml, seq, timing, instruments } = data;
  const snapshot = useMemo<ScoreSnapshot | null>(
    () => (score && xml !== null ? { xml, transcription: score, seq } : null),
    [score, xml, seq],
  );
  const expected = useMemo(() => (score ? measuresPerStaff(score) : []), [score]);
  const playback = useMemo(
    () => (score && timing ? buildPlayback(score, timing, instruments) : null),
    [score, timing, instruments],
  );
  const player = usePlayer(playback);
  const playing = useMemo(
    () =>
      score && player.measure !== null
        ? { measure: player.measure, slots: measureSlots(score, player.measure) }
        : null,
    [score, player.measure],
  );

  return (
    <section className="landing-result" aria-labelledby="landing-result-title">
      <div className="landing-result__head">
        <p className="label landing-result__kicker">Transcrita</p>
        <h3
          id="landing-result-title"
          className="landing-result__title"
          ref={headingRef}
          tabIndex={-1}
        >
          {data.name}
        </h3>
        {data.findingsCount !== null && (
          <p className="landing-result__findings">
            <span className={data.findingsCount > 0 ? "chip chip--finding" : "chip chip--done"}>
              {findingsText(data.findingsCount)}
            </span>
            <span className="landing-result__caveat">
              Las reglas no lo detectan todo: revisa toda la transcripción al editarla.
            </span>
          </p>
        )}
        <div className="landing-result__actions">{actions}</div>
      </div>

      <figure className="sheet sheet--notation landing-result__sheet">
        <figcaption className="label sheet__caption">Transcripción · solo lectura</figcaption>
        <div className="sheet__transport">
          <PlaybackBar
            status={player.status}
            measure={player.measure}
            announcement={player.announcement}
            tempo={player.tempo}
            totalBeats={playback ? playback.totalBeats : null}
            measureCount={playback?.measures.length ?? 0}
            silent={playback !== null && playback.notes.length === 0}
            failure={data.timingFailed ? "timing" : player.loadFailed ? "load" : null}
            onRetry={() => {
              if (data.timingFailed) data.onRetry?.();
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
            sessionId={data.viewKey}
            marks={[]}
            expectedMeasures={expected}
            selectedKey={null}
            findingsListed={false}
            playing={playing}
            notesSelectable={false}
          />
        ) : data.failure ? (
          <div className="notation__failed" role="alert">
            <p className="notation__failed-title">No se pudo cargar la partitura.</p>
            <p>{data.failure}</p>
            {data.onRetry && (
              <button type="button" className="link-button" onClick={data.onRetry}>
                Reintentar
              </button>
            )}
          </div>
        ) : (
          <p className="label landing-result__loading" role="status">
            Cargando la partitura…
          </p>
        )}
      </figure>
    </section>
  );
}

interface SessionResultProps {
  sessionId: string;
  /** Nombre que se enseña mientras llega el de la sesión: el dado o el del archivo. */
  provisionalName?: string;
  findingsCount: number;
  /** Condición de la sesión: en la no asistida no se habla de posibles errores (ADR-0040). */
  condition?: string;
  headingRef?: Ref<HTMLHeadingElement>;
  onAnother: () => void;
}

/**
 * El resultado de una transcripción con sesión (#277): lo que se enseña sale de la sesión recién
 * creada, con las mismas consultas que su vista, que así la abre sin volver a pedirlo.
 */
export function SessionResult({
  sessionId,
  provisionalName,
  findingsCount,
  condition,
  headingRef,
  onAnother,
}: SessionResultProps) {
  const detail = useQuery(sessionDetailQuery(api, sessionId));
  const seq = detail.data?.current_seq ?? 0;
  const ready = detail.isSuccess;
  const musicXml = useQuery({ ...sessionMusicXmlQuery(api, sessionId, seq), enabled: ready });
  const timing = useQuery({ ...sessionTimingQuery(api, sessionId, seq), enabled: ready });

  const failed = detail.isError ? detail.error : musicXml.isError ? musicXml.error : null;
  const data: ResultData = {
    viewKey: sessionId,
    name: detail.data
      ? sessionName({
          session_id: sessionId,
          title: detail.data.title,
          source_filename: detail.data.source_filename,
        })
      : (provisionalName ?? sessionName({ session_id: sessionId })),
    findingsCount: condition === "unassisted" ? null : findingsCount,
    score: detail.data?.current_score ?? null,
    xml: musicXml.data ?? null,
    seq,
    timing: timing.data ?? null,
    instruments: detail.data?.instruments,
    failure: failed ? errorMessage(failed) : null,
    onRetry: () => {
      if (detail.isError) void detail.refetch();
      else if (musicXml.isError) void musicXml.refetch();
      else if (timing.isError) void timing.refetch();
    },
    timingFailed: timing.isError,
  };

  return (
    <ResultView
      data={data}
      headingRef={headingRef}
      actions={
        <>
          <Link
            className="button button--primary"
            to={`/sesiones/${encodeURIComponent(sessionId)}`}
          >
            Editar
            <PixelIcon name="arrow-right" />
          </Link>
          <button type="button" className="link-button" onClick={onAnother}>
            Transcribir otra imagen
          </button>
        </>
      }
    />
  );
}

interface PreviewResultProps {
  preview: PreviewResponse;
  /** Nombre que se le dio, o el del archivo. */
  name: string;
  headingRef?: Ref<HTMLHeadingElement>;
  /** «Editar» y lo demás: entrar, crear la cuenta o abrirla, según haya sesión. */
  actions: ReactNode;
  /** Aviso junto a las acciones (que hay que entrar, que caducó la sesión…). */
  note: ReactNode;
}

/**
 * El resultado de una transcripción sin cuenta (#278, ADR-0054): lo que leyó HOMR viene en la
 * respuesta de `POST /previews` (MusicXML, `ScoreIR` y tiempos), sin ninguna otra petición.
 */
export function PreviewResult({ preview, name, headingRef, actions, note }: PreviewResultProps) {
  const data: ResultData = {
    viewKey: `vista-previa-${preview.preview_id}`,
    name: nonBlank(preview.title) ?? name,
    findingsCount: preview.findings_count,
    score: preview.score,
    xml: preview.musicxml ?? null,
    seq: 0,
    timing: preview.timing,
    instruments: preview.instruments,
    failure:
      preview.musicxml == null
        ? "No se pudo preparar la partitura para verla; al editarla se vuelve a intentar."
        : null,
    timingFailed: false,
  };
  return (
    <ResultView
      data={data}
      headingRef={headingRef}
      actions={
        <>
          {actions}
          <div className="landing-result__note">{note}</div>
        </>
      }
    />
  );
}
