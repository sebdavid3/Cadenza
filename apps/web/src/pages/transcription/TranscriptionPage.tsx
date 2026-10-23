import { useDocumentTitle } from "../../hooks/useDocumentTitle";

// Base de la zona privada: la cola de imágenes y el listado de sesiones llegan en #147.
export function TranscriptionPage() {
  useDocumentTitle("Transcripción");

  return (
    <main style={{ padding: "var(--space-7) var(--gutter)" }}>
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-heading)",
          textTransform: "uppercase",
        }}
      >
        Transcripción
      </h1>
    </main>
  );
}
