import { useDocumentTitle } from "../../hooks/useDocumentTitle";

// Base provisional de la landing: la página completa llega en #145.
export function LandingPage() {
  useDocumentTitle();

  return (
    <main style={{ padding: "var(--space-8) var(--gutter)" }}>
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "var(--text-display)",
          lineHeight: 0.86,
          textTransform: "uppercase",
        }}
      >
        Cadenza
      </h1>
      <p style={{ marginTop: "var(--space-5)", maxWidth: "48ch", fontSize: "var(--text-lead)" }}>
        De la imagen de una partitura impresa a notación editable.
      </p>
    </main>
  );
}
