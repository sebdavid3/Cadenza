import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  AnchorPayload,
  ScoreEventPayload,
  ScoreIRPayload,
  TimeSignaturePayload,
} from "../../types";
import { planCommand, type EditTarget } from "./edits";
import { TimePicker } from "./TimePicker";

const C4: ScoreEventPayload = {
  kind: "note",
  voice: 0,
  pitch: "C4",
  duration_beats: "3",
  tie: null,
  is_chord: false,
  bbox: null,
  confidence: null,
  ir_handle: null,
};

/** La voz y el piano; cada pentagrama, el compás de cada uno de sus compases. */
function voiceAndPiano(
  voice: (TimeSignaturePayload | null)[],
  piano: (TimeSignaturePayload | null)[],
): ScoreIRPayload {
  const staff = (part: number, index: number, signatures: (TimeSignaturePayload | null)[]) => ({
    id: `part-${String(part)}-staff-${String(index)}`,
    measures: signatures.map((signature, position) => ({
      number: position + 1,
      events: [C4],
      time_signature: signature,
    })),
  });
  return {
    parts: [
      { id: "part-0", staves: [staff(0, 0, voice)] },
      { id: "part-1", staves: [staff(1, 0, piano), staff(1, 1, piano)] },
    ],
  };
}

const leftHand: AnchorPayload = {
  part: 1,
  staff: 1,
  measure: 1,
  voice: 0,
  event_index: 0,
  staff_id: "part-1-staff-1",
  bbox: null,
  confidence: null,
};
const target: EditTarget = { anchor: leftHand, event: C4, chord: false };

function renderPicker(score: ScoreIRPayload) {
  const onRun = vi.fn();
  render(
    <>
      <span id="time-label">Compás</span>
      <TimePicker
        labelId="time-label"
        target={target}
        score={score}
        blocked={false}
        onRun={onRun}
      />
    </>,
  );
  return onRun;
}

describe("TimePicker con varias partes (#326)", () => {
  it("muestra el compás de la nota elegida aunque venga de otra parte", () => {
    // El compás puesto solo en la voz (antes de #326): el piano no lleva ninguno.
    const score = voiceAndPiano([{ beats: 3, beat_type: 4 }, null], [null, null]);
    const onRun = renderPicker(score);
    expect(screen.getByRole("combobox", { name: "Compás" })).toHaveValue("3/4");
    // No es «el mismo»: el piano no lo tiene. Una pulsación lo pone en todas las partes.
    const change = screen.getByRole("button", { name: "Cambiar compás" });
    expect(change).toHaveAttribute("aria-disabled", "false");
    fireEvent.click(change);
    expect(onRun).toHaveBeenCalledTimes(1);
    const command = onRun.mock.calls[0]?.[0] as Parameters<typeof planCommand>[0];
    expect(planCommand(command, target, score)).toMatchObject({
      kind: "edit",
      op: "SetTime",
      after: { time_signature: { beats: 3, beat_type: 4 }, all_parts: true },
      change: "compás 3/4 en los compases 1 a 2, en todas las partes",
    });
  });

  it("sin compás en ninguna parte propone 4/4, y con todas iguales «Cambiar» no hace nada", () => {
    const { unmount } = render(
      <>
        <span id="time-label">Compás</span>
        <TimePicker
          labelId="time-label"
          target={target}
          score={voiceAndPiano([null], [null])}
          blocked={false}
          onRun={vi.fn()}
        />
      </>,
    );
    expect(screen.getByRole("combobox", { name: "Compás" })).toHaveValue("4/4");
    unmount();
    const three = { beats: 3, beat_type: 4 };
    renderPicker(voiceAndPiano([three], [three]));
    expect(screen.getByRole("button", { name: "Cambiar compás" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});
