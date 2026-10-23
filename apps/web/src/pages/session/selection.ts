import { create } from "zustand";
import type { AnchorPayload } from "../../types";

/**
 * Evento elegido sobre la partitura. El ancla es relativa al estado `seq` de la sesión
 * (ADR-0011): con otro estado deja de valer y la vista no la muestra.
 */
export interface NoteSelection {
  sessionId: string;
  seq: number;
  anchor: AnchorPayload;
}

interface SelectionState {
  selection: NoteSelection | null;
  select: (selection: NoteSelection) => void;
  clear: () => void;
}

/** Estado editorial de la vista de una sesión (ADR-0006, ADR-0027): la nota elegida. */
export const useSelectionStore = create<SelectionState>()((set) => ({
  selection: null,
  select: (selection) => {
    set({ selection });
  },
  clear: () => {
    set({ selection: null });
  },
}));
