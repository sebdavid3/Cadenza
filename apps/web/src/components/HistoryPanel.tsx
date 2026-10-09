import { useEditorStore } from "../store/editorStore";

export function HistoryPanel() {
  const history = useEditorStore((state) => state.history);
  const cursor = useEditorStore((state) => state.cursor);
  const undo = useEditorStore((state) => state.undo);
  const redo = useEditorStore((state) => state.redo);

  return (
    <div className="history">
      <div className="history-toolbar">
        <button type="button" onClick={undo} disabled={cursor === 0}>
          Deshacer
        </button>
        <button type="button" onClick={redo} disabled={cursor >= history.length}>
          Rehacer
        </button>
        <span className="muted">
          {cursor}/{history.length}
        </span>
      </div>
      <ol className="history-list">
        {history.map((edit, index) => (
          <li key={edit.id} className={index < cursor ? "applied" : "undone"}>
            #{edit.seq} {edit.op} · compás {edit.anchor.measure}
          </li>
        ))}
      </ol>
    </div>
  );
}
