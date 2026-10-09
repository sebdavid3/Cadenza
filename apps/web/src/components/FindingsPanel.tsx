import { useEditorStore } from "../store/editorStore";

export function FindingsPanel() {
  const findings = useEditorStore((state) => state.session?.findings ?? []);
  const selectAnchor = useEditorStore((state) => state.selectAnchor);

  if (findings.length === 0) {
    return <p className="muted">Sin hallazgos de validación.</p>;
  }

  return (
    <ul className="findings">
      {findings.map((finding) => (
        <li key={finding.id} className={`finding finding--${finding.severity}`}>
          <button type="button" onClick={() => selectAnchor(finding.anchor)}>
            <strong>{finding.rule_id}</strong>
            <span>{finding.message}</span>
            {finding.suggested_fix && <em>{finding.suggested_fix}</em>}
          </button>
        </li>
      ))}
    </ul>
  );
}
