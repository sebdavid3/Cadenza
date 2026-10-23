/** Resuelve cuando las tipografías del documento están cargadas (al instante si el navegador no lo expone). */
export function whenFontsReady(): Promise<unknown> {
  return "fonts" in document ? document.fonts.ready : Promise.resolve();
}
