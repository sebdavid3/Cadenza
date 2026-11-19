import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DrawnBarRead } from "../../types";
import { EngravedBar } from "./EngravedBar";
import { FIGURES } from "./fixtures";

const engrave = vi.hoisted(() => vi.fn<(host: HTMLElement, xml: string) => Promise<void>>());

vi.mock("./engrave", () => ({
  canEngrave: () => true,
  accentColor: () => "#7a2cf0",
  engrave,
}));

const BAR: DrawnBarRead = {
  clef: "G2",
  key: -1,
  read: [
    { kind: "note", pitch: "Bb4", beats: "1", chord: false },
    { kind: "note", pitch: "C5", beats: "1/2", chord: false },
  ],
  fixed: [
    { kind: "note", pitch: "B4", beats: "1", chord: false },
    { kind: "note", pitch: "C5", beats: "1", chord: false },
  ],
};

afterEach(() => {
  engrave.mockReset();
});

describe("el compás grabado con OSMD", () => {
  it("graba lo leído y lo correcto, cada uno en su pentagrama, con la nota en violeta", async () => {
    engrave.mockResolvedValue(undefined);
    render(<EngravedBar bar={BAR} atRead={1} atFix={1} measure="3" figures={FIGURES} />);

    expect(
      screen.getByRole("img", { name: "Compás 3: lo que leyó HOMR y lo correcto" }),
    ).toHaveClass("homr__engraved");
    await waitFor(() => {
      expect(engrave).toHaveBeenCalledTimes(2);
    });
    const [read, fixed] = engrave.mock.calls.map(([, xml]) => xml);
    expect(read).toContain("<step>B</step><alter>-1</alter>");
    expect(fixed).toContain("<step>B</step><octave>4</octave>");
    expect(read).toMatch(/<note color="#7a2cf0">.*<step>C<\/step>/);
  });

  it("si OSMD no puede, lo dibuja como el informe", async () => {
    engrave.mockRejectedValue(new Error("OSMD no pudo"));
    const { container } = render(
      <EngravedBar bar={BAR} atRead={1} atFix={1} measure="3" figures={FIGURES} />,
    );

    await waitFor(() => {
      expect(container.querySelector(".homr__drawn")).not.toBeNull();
    });
    expect(container.querySelector(".homr__engraved")).toBeNull();
  });
});
