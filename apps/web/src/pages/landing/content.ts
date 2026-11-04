// Textos de la landing que comparten la demostración y la sección «Cómo funciona».

export interface Step {
  title: string;
  text: string;
  caption: string;
}

export const STEPS: readonly Step[] = [
  {
    title: "Sube las imágenes",
    text: "Imágenes PNG o JPEG de partituras impresas, de hasta 20 MB. Puedes subir varias: se transcriben en cola, una tras otra.",
    caption: "La imagen",
  },
  {
    title: "HOMR transcribe",
    text: "Un motor de reconocimiento óptico de música lee la imagen y propone la partitura como notación. Cada imagen abre una sesión de trabajo.",
    caption: "Lo que lee el motor",
  },
  {
    title: "Las reglas señalan la duda",
    text: "Un validador revisa la duración de cada compás, la armadura, el registro y otras reglas musicales, y marca lo sospechoso. No cambia nada por su cuenta ni lo detecta todo.",
    caption: "Compás 3: cuatro tiempos en un 3/4",
  },
  {
    title: "Tú decides",
    text: "Corriges sobre la notación. Cada cambio queda registrado, con su autor y su orden, y se puede deshacer. La corrección en el navegador está en construcción.",
    caption: "Compás 3 corregido: dos corcheas",
  },
];
