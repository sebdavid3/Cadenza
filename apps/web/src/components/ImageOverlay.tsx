import { useState } from "react";

import { anchorKey, useEditorStore } from "../store/editorStore";

export function ImageOverlay() {
  const imageUrl = useEditorStore((state) => state.imageUrl);
  const entries = useEditorStore((state) => state.session?.document.anchors.entries ?? []);
  const findings = useEditorStore((state) => state.session?.findings ?? []);
  const selected = useEditorStore((state) => state.selected);
  const selectAnchor = useEditorStore((state) => state.selectAnchor);
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);

  const findingKeys = new Set(findings.map((finding) => anchorKey(finding.anchor)));
  const selectedKey = selected ? anchorKey(selected) : null;

  return (
    <div className="stage">
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="Partitura original"
          className="stage-image"
          onLoad={(event) =>
            setNatural({
              width: event.currentTarget.naturalWidth,
              height: event.currentTarget.naturalHeight,
            })
          }
        />
      ) : (
        <p className="muted">Sin imagen</p>
      )}
      {natural &&
        entries.map(({ anchor }) => {
          if (!anchor.bbox) {
            return null;
          }
          const key = anchorKey(anchor);
          const [x0, y0, x1, y1] = anchor.bbox;
          const classes = ["overlay-box"];
          if (findingKeys.has(key)) {
            classes.push("overlay-box--finding");
          }
          if (key === selectedKey) {
            classes.push("overlay-box--selected");
          }
          return (
            <button
              key={key}
              type="button"
              className={classes.join(" ")}
              style={{
                left: `${(x0 / natural.width) * 100}%`,
                top: `${(y0 / natural.height) * 100}%`,
                width: `${((x1 - x0) / natural.width) * 100}%`,
                height: `${((y1 - y0) / natural.height) * 100}%`,
              }}
              title={`${anchor.staff_id} · compás ${anchor.measure}`}
              onClick={() => selectAnchor(anchor)}
            />
          );
        })}
    </div>
  );
}
