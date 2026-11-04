import { useEffect, useRef, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { api } from "../../api/instance";
import { useAuthStore } from "../../auth/store";
import "../../components/button.css";
import { anonymousPreviewEnabled, registrationEnabled } from "../../config";
import { formatSize } from "../transcription/format";
import { Elapsed } from "../transcription/QueuePanel";
import { ScoreDataFields, type PartField } from "../transcription/ScoreDataFields";
import { nonBlank } from "../transcription/scoreData";
import { useBlockStrayDrops } from "../transcription/useBlockStrayDrops";
import { UploadZone } from "../transcription/UploadZone";
import "./landing-upload.css";
import { PreviewResult, SessionResult } from "./LandingResult";
import {
  expiryTime,
  LANDING_UPLOAD_HASH,
  LANDING_UPLOAD_PATH,
  useLandingUpload,
} from "./uploadStore";

/** Las dos partes que se piden, como en «Antes de transcribir» (ADR-0045 §1). */
const PARTS: PartField[] = [
  { label: "Parte de arriba", hint: "La voz o el instrumento del pentagrama de arriba." },
  {
    label: "Segunda parte",
    hint: "El piano que acompaña, si lo hay. Si la partitura no la tiene, se ignora.",
  },
];

const HINT = "o arrástrala aquí. Una imagen PNG o JPEG de una partitura impresa, de hasta 20 MB.";

/** Adonde se vuelve tras entrar o crear la cuenta: esta sección de la portada. */
const RETURN_STATE = { from: LANDING_UPLOAD_PATH };

/**
 * Recuadro de la portada para transcribir una imagen (#277, ADR-0053): se elige la imagen, se le
 * dan nombre e instrumentos (#240) y, con la sesión iniciada, se transcribe y se ve el resultado
 * aquí mismo; para editarlo se abre su sesión. Sin sesión se pide entrar o crear la cuenta, y al
 * volver la transcripción sigue sola con la imagen y los datos, que esperan en memoria.
 *
 * Si el despliegue transcribe sin cuenta (#278, ADR-0054), sin sesión se transcribe igual y se ve
 * el resultado; «Editar» pide entrar y, al volver, la transcripción se reclama y se abre su sesión.
 */
export function LandingUpload() {
  const location = useLocation();
  const status = useAuthStore((state) => state.status);
  const file = useLandingUpload((state) => state.file);
  const draft = useLandingUpload((state) => state.draft);
  const stage = useLandingUpload((state) => state.stage);
  const resumeAfterAuth = useLandingUpload((state) => state.resumeAfterAuth);
  const expired = useLandingUpload((state) => state.expired);
  const rejection = useLandingUpload((state) => state.rejection);
  const lostFile = useLandingUpload((state) => state.lostFile);
  const previewsOff = useLandingUpload((state) => state.previewsOff);
  const claimAfterAuth = useLandingUpload((state) => state.claimAfterAuth);
  const {
    choose,
    setDraft,
    discard,
    requestAuth,
    detectLost,
    dismissLost,
    transcribe,
    preview,
    requestClaim,
    claim,
    detectPendingClaim,
  } = useLandingUpload.getState();
  const navigate = useNavigate();

  const sectionRef = useRef<HTMLElement>(null);
  const chooseRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLHeadingElement>(null);
  const failureRef = useRef<HTMLParagraphElement>(null);
  const authRef = useRef<HTMLParagraphElement>(null);

  // Mientras se ve el recuadro, soltar un archivo fuera de la zona no abre la imagen en la
  // pestaña: se perdería lo elegido o el resultado (también mientras se transcribe).
  useBlockStrayDrops();

  // Una imagen que esperaba a que se entrara y ya no está: la página se recargó.
  // Y una transcripción sin cuenta que espera a reclamarse (su token sobrevive a la recarga).
  useEffect(() => {
    detectLost();
    detectPendingClaim();
  }, [detectLost, detectPendingClaim]);

  // Al volver de entrar, la sección se trae a la vista (el enrutador no sigue el ancla).
  const hash = location.hash;
  useEffect(() => {
    if (hash !== LANDING_UPLOAD_HASH) return;
    sectionRef.current?.scrollIntoView({ block: "start" });
  }, [hash]);

  // Se pidió entrar para transcribir: al volver de entrar (con el ancla de la sección, que es
  // adonde lleva el acceso) y con la sesión ya iniciada, sigue sola. Si se entró por otro camino,
  // no se envía nada sin pulsar.
  const authenticated = status === "authenticated";
  const returned = hash === LANDING_UPLOAD_HASH;
  useEffect(() => {
    if (authenticated && returned && resumeAfterAuth && file && stage.kind === "chosen") {
      void transcribe(api);
    }
  }, [authenticated, returned, resumeAfterAuth, file, stage.kind, transcribe]);

  // Lo mismo con la transcripción sin cuenta: al volver de entrar para editarla, se reclama. Tras
  // una recarga solo queda su token, y volver de entrar basta para reclamarla.
  // Una sola vez por transcripción: si falla, se reintenta con «Editar», no en bucle.
  const pendingPreview = stage.kind === "previewed" ? stage.preview : undefined;
  const pendingClaimId = stage.kind === "previewed" ? stage.claim.id : null;
  const autoClaimed = useRef<string | null>(null);
  useEffect(() => {
    if (!authenticated || !returned || pendingClaimId === null) return;
    if (autoClaimed.current === pendingClaimId) return;
    if (claimAfterAuth || pendingPreview === null) {
      autoClaimed.current = pendingClaimId;
      void claim(api);
    }
  }, [authenticated, returned, pendingClaimId, claimAfterAuth, pendingPreview, claim]);

  // Ir a entrar para editarla vuelve a permitir que se reclame sola al volver.
  const loginToEdit = () => {
    autoClaimed.current = null;
    requestClaim();
  };

  // Reclamada: ya es una sesión, y se abre para editarla.
  const claimedId = stage.kind === "claimed" ? stage.sessionId : null;
  useEffect(() => {
    if (claimedId === null) return;
    discard();
    void navigate(`/sesiones/${encodeURIComponent(claimedId)}`, { replace: true });
  }, [claimedId, discard, navigate]);

  // El foco acompaña a cada paso: al nombre tras elegir la imagen, al progreso al enviarla, al
  // resultado o al error al terminar.
  const previousStage = useRef(stage.kind);
  useEffect(() => {
    const before = previousStage.current;
    previousStage.current = stage.kind;
    if (before === stage.kind) return;
    if (stage.kind === "transcribing" || stage.kind === "claiming") progressRef.current?.focus();
    else if (stage.kind === "done" || stage.kind === "previewed") resultRef.current?.focus();
    else if (stage.kind === "failed") failureRef.current?.focus();
    // La sesión caducó al enviar: el aviso de volver a entrar se lleva el foco.
    else if (before === "transcribing" && stage.kind === "chosen") authRef.current?.focus();
  }, [stage.kind]);
  const previousFile = useRef(file);
  useEffect(() => {
    const before = previousFile.current;
    previousFile.current = file;
    if (file && file !== before && stage.kind === "chosen") titleRef.current?.focus();
  }, [file, stage.kind]);

  // Sin sesión, se transcribe sin cuenta si el despliegue lo abre y el servidor no dijo que no.
  const anonymous = !authenticated && status !== "restoring";
  const canPreview = anonymous && anonymousPreviewEnabled() && !previewsOff;
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (authenticated) void transcribe(api);
    else if (canPreview) void preview(api);
  };

  // Al descartar, el foco vuelve a «Elegir una imagen», que puede no estar aún en pantalla (tras
  // un resultado): se lleva cuando aparece.
  const focusChoose = useRef(false);
  useEffect(() => {
    if (!focusChoose.current || !chooseRef.current) return;
    focusChoose.current = false;
    chooseRef.current.focus();
  });
  const onDiscard = () => {
    focusChoose.current = true;
    discard();
  };

  const busy = stage.kind === "transcribing" || stage.kind === "claiming";
  const showForm = file !== null && (stage.kind === "chosen" || stage.kind === "failed");
  const name = file ? (nonBlank(draft.title) ?? file.name) : "";

  return (
    <section
      id="transcribir"
      ref={sectionRef}
      className="landing-upload"
      aria-labelledby="landing-upload-title"
    >
      <h2 id="landing-upload-title" className="section-title">
        Transcribe una partitura
      </h2>
      <div className="landing-upload__body">
        <p className="landing-upload__lead">
          Sube la imagen de una partitura impresa y mira aquí lo que lee HOMR: la partitura, cómo
          suena y cuántos posibles errores señalan las reglas. Para corregirla, ábrela en su sesión.
        </p>

        {stage.kind === "previewed" ? (
          stage.preview ? (
            <PreviewResult
              preview={stage.preview}
              name={stage.claim.name}
              headingRef={resultRef}
              actions={
                <PreviewActions
                  authenticated={authenticated}
                  onEdit={() => void claim(api)}
                  onLogin={loginToEdit}
                  onAnother={onDiscard}
                />
              }
              note={
                <PreviewNote
                  authenticated={authenticated}
                  expired={expired}
                  expiresAt={stage.claim.expiresAt}
                />
              }
            />
          ) : (
            <section className="landing-upload__pending" aria-labelledby="landing-pending-title">
              <h3 id="landing-pending-title" className="panel__title" ref={resultRef} tabIndex={-1}>
                Transcripción sin cuenta
              </h3>
              <p>
                «{stage.claim.name}» está transcrita sin cuenta y se guarda hasta las{" "}
                {expiryTime(stage.claim.expiresAt)}.{" "}
                {authenticated ? "Ábrela para editarla." : "Entra para editarla."}
              </p>
              <div className="landing-upload__actions">
                <PreviewActions
                  authenticated={authenticated}
                  onEdit={() => void claim(api)}
                  onLogin={loginToEdit}
                  onAnother={onDiscard}
                />
              </div>
            </section>
          )
        ) : stage.kind === "done" ? (
          <SessionResult
            sessionId={stage.result.session_id}
            provisionalName={stage.name}
            findingsCount={stage.result.findings_count}
            condition={stage.result.condition}
            headingRef={resultRef}
            onAnother={onDiscard}
          />
        ) : busy ? (
          <div
            className="landing-upload__progress"
            ref={progressRef}
            tabIndex={-1}
            role="status"
            aria-live="polite"
          >
            {stage.kind === "claiming" ? (
              <p className="landing-upload__progress-title">
                Abriendo «{stage.claim.name}» para editarla…
              </p>
            ) : (
              <>
                <p className="landing-upload__progress-title">
                  Transcribiendo «{name}»
                  <Elapsed since={stage.startedAt} />
                </p>
                <p className="landing-upload__progress-note">
                  HOMR lee la imagen y propone la partitura; suele tardar unos segundos y puede
                  llegar a 30. No hace falta quedarse mirando: el resultado aparecerá aquí.
                </p>
              </>
            )}
          </div>
        ) : (
          <UploadZone
            className="upload landing-upload__zone"
            onFiles={choose}
            buttonRef={chooseRef}
            multiple={false}
            buttonLabel={file ? "Elegir otra imagen" : "Elegir una imagen"}
            hint={HINT}
          />
        )}

        {/* Tras la zona en el DOM, como se ve: el orden del tabulador sigue al visual. */}
        {lostFile !== null && (
          <div className="landing-upload__notice" role="alert">
            <p>
              La página se recargó y la imagen «{lostFile}» se perdió: Cadenza no la guarda en el
              navegador. Vuelve a elegirla, y a escribir sus datos, para transcribirla.
            </p>
            <button type="button" className="link-button" onClick={dismissLost}>
              Entendido
            </button>
          </div>
        )}

        {rejection !== null && !busy && stage.kind !== "done" && (
          <p className="landing-upload__error" role="alert">
            {rejection}
          </p>
        )}

        {showForm && (
          <form
            className="landing-upload__form"
            aria-labelledby="landing-upload-form-title"
            onSubmit={onSubmit}
            noValidate
          >
            <div className="landing-upload__file">
              <h3 id="landing-upload-form-title" className="panel__title">
                Antes de transcribir
              </h3>
              <p className="landing-upload__name">
                {file.name}
                <span className="label landing-upload__size">{formatSize(file.size)}</span>
              </p>
            </div>
            {stage.kind === "failed" && (
              <p className="landing-upload__error" role="alert" ref={failureRef} tabIndex={-1}>
                {stage.message}
                {stage.timedOut && (
                  <>
                    {" "}
                    <Link to="/transcripcion">Ver tus sesiones</Link>
                  </>
                )}
              </p>
            )}
            <fieldset className="landing-upload__fields">
              <legend className="prepare__legend">Datos de la partitura</legend>
              <ScoreDataFields
                value={draft}
                onChange={setDraft}
                parts={PARTS}
                titleRef={titleRef}
                titleHint="Todo es opcional. Sin nombre, la sesión se llama como el archivo."
              />
            </fieldset>
            {authenticated || canPreview ? (
              <div className="landing-upload__actions">
                <button type="submit" className="button button--primary">
                  {stage.kind === "failed" ? "Volver a intentarlo" : "Transcribir la imagen"}
                </button>
                <button type="button" className="link-button" onClick={onDiscard}>
                  Descartar
                </button>
                {canPreview && (
                  <p className="landing-upload__hint">
                    Sin cuenta: la transcripción se guarda una hora para que puedas editarla al
                    entrar o crear una cuenta. Si recargas la página antes de transcribirla, tendrás
                    que volver a elegir la imagen.
                  </p>
                )}
              </div>
            ) : status === "restoring" ? (
              <div className="landing-upload__actions">
                <button type="submit" className="button button--primary" disabled>
                  Comprobando la sesión…
                </button>
              </div>
            ) : (
              <div className="landing-upload__auth" role="group" aria-labelledby="landing-auth">
                <p
                  id="landing-auth"
                  className="landing-upload__auth-text"
                  ref={authRef}
                  tabIndex={-1}
                >
                  {expired
                    ? "Tu sesión caducó antes de transcribirla. Vuelve a entrar: la imagen y sus datos siguen aquí y la transcripción empezará al volver."
                    : `${previewsOff ? "Ahora no se puede transcribir sin cuenta. " : ""}Para transcribir hace falta entrar. La imagen y sus datos esperan aquí mientras tanto, y la transcripción empieza al volver.`}{" "}
                  Si recargas la página, tendrás que volver a elegir la imagen.
                </p>
                <div className="landing-upload__actions">
                  <Link
                    className="button button--primary"
                    to="/entrar"
                    state={RETURN_STATE}
                    onClick={requestAuth}
                  >
                    Entrar y transcribir
                  </Link>
                  {registrationEnabled() && (
                    <Link
                      className="button"
                      to="/registro"
                      state={RETURN_STATE}
                      onClick={requestAuth}
                    >
                      Crear una cuenta
                    </Link>
                  )}
                  <button type="button" className="link-button" onClick={onDiscard}>
                    Descartar
                  </button>
                </div>
              </div>
            )}
          </form>
        )}
      </div>
    </section>
  );
}

interface PreviewActionsProps {
  authenticated: boolean;
  onEdit: () => void;
  onLogin: () => void;
  onAnother: () => void;
}

/**
 * Las acciones de una transcripción sin cuenta: con sesión, «Editar» la reclama y abre la sesión;
 * sin ella, se entra o se crea la cuenta y, al volver, se reclama sola (ADR-0054).
 */
function PreviewActions({ authenticated, onEdit, onLogin, onAnother }: PreviewActionsProps) {
  return (
    <>
      {authenticated ? (
        <button type="button" className="button button--primary" onClick={onEdit}>
          Editar
        </button>
      ) : (
        <>
          <Link
            className="button button--primary"
            to="/entrar"
            state={RETURN_STATE}
            onClick={onLogin}
          >
            Entrar para editarla
          </Link>
          {registrationEnabled() && (
            <Link className="button" to="/registro" state={RETURN_STATE} onClick={onLogin}>
              Crear una cuenta
            </Link>
          )}
        </>
      )}
      <button type="button" className="link-button" onClick={onAnother}>
        Transcribir otra imagen
      </button>
    </>
  );
}

function PreviewNote({
  authenticated,
  expired,
  expiresAt,
}: {
  authenticated: boolean;
  expired: boolean;
  expiresAt: number;
}) {
  if (expired) {
    return (
      <p className="landing-upload__hint" role="alert">
        Tu sesión caducó antes de abrirla. Vuelve a entrar: la transcripción sigue guardada.
      </p>
    );
  }
  return (
    <p className="landing-upload__hint">
      {authenticated
        ? "Al editarla pasa a ser una sesión tuya."
        : "Sin cuenta solo se puede ver: para editarla, entra o crea una cuenta y pasará a ser una sesión tuya."}{" "}
      Se guarda hasta las {expiryTime(expiresAt)}; después se borra con la imagen.
    </p>
  );
}
