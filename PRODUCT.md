# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Decidido en `docs/ARCHITECTURE.md` (tabla de stack) y ADR-0006: React 18 + TypeScript + Vite en `apps/web`, Zustand para el estado del editor y TanStack Query para el estado del servidor, ESLint y Vitest; Playwright está previsto, pero todavía no se usa. El cliente consume la API v1 congelada (`docs/api/openapi.json`) con los tipos generados en `apps/web/src/types.ts`.

## Users

- **Transcriptores.** Digitalizan partituras impresas por lotes: suben muchas imágenes en una jornada, siguen el estado de cada una y después revisan y corrigen la transcripción propuesta. Solo ven sus propias sesiones.
- **Investigadores.** Crean las cuentas del estudio, pueden desactivar las del registro, ven las sesiones de todos y auditan el trabajo. También pueden transcribir.
- **Visitantes de la página pública.** Archivos, bibliotecas y músicos que pueden registrarse y probarlo en el momento (registro abierto desde el 2026-10-23). Les interesa el uso, no la investigación.

## Product Purpose

Cadenza convierte la imagen de una partitura en notación editable (MusicXML y MIDI). Un motor de reconocimiento óptico de música (HOMR) propone la transcripción, un validador de reglas musicales señala los compases sospechosos y una persona la corrige. Cada corrección se guarda como un evento inmutable que sirve después para entrenar al sistema. Es el proyecto de una tesis.

El éxito es que una persona digitalice una partitura con menos esfuerzo que transcribiéndola a mano y sin perder el control sobre el resultado.

## Positioning

No es un reconocimiento automático que entrega un resultado cerrado: la máquina propone y señala dónde dudar, y la persona decide. Las correcciones no se pierden: quedan como un registro inmutable, con autor y orden, que se puede deshacer y que alimenta el aprendizaje del sistema.

## Operating Context

- La transcripción es síncrona: una imagen por petición, de unos segundos en el peor caso documentado, con imágenes PNG o JPEG de hasta 20 MB.
- Cada imagen crea una sesión de trabajo con hallazgos del validador. Hoy la sesión se revisa, se descarga y se escucha; la corrección sobre la partitura está planificada ([#182](https://github.com/sebdavid3/Cadenza/issues/182)–[#186](https://github.com/sebdavid3/Cadenza/issues/186)).
- Cualquiera puede crear una cuenta en `/registro` (solo usuario y contraseña) y entra en el momento; un investigador puede desactivarla en `/cuentas`. Los investigadores también crean cuentas para el estudio, que no se mezclan con las del registro (ADR-0022, ADR-0025). No hay recuperación de contraseña por correo. La sesión del navegador dura 30 minutos y no se renueva.

## Capabilities and Constraints

- HOMR es el único motor y solo se ha evaluado sobre PrIMuS: incipits impresos y monofónicos. SMB y MUSCIMA++ no están evaluados (#102). No se prometen manuscritos ni polifonía densa.
- HOMR no da coordenadas por nota: la interfaz no puede resaltar notas sobre la imagen original. La imagen es una referencia global.
- La interfaz va en español.
- La vista de una sesión descarga el MusicXML ([#176](https://github.com/sebdavid3/Cadenza/issues/176)) y la reproduce con el compás que suena resaltado ([#177](https://github.com/sebdavid3/Cadenza/issues/177)). Planificados en la Fase 8: la corrección ([#182](https://github.com/sebdavid3/Cadenza/issues/182)–[#186](https://github.com/sebdavid3/Cadenza/issues/186)), el cierre y la descarga del MIDI ([#187](https://github.com/sebdavid3/Cadenza/issues/187)–[#189](https://github.com/sebdavid3/Cadenza/issues/189)) y el cambio de contraseña ([#190](https://github.com/sebdavid3/Cadenza/issues/190)); el detalle está en `docs/phases/phase_8_web_interface/README.md`.

## Brand Commitments

- El nombre es Cadenza y firma solo Cadenza: sin universidad, autor ni logos (confirmado el 2026-10-22).
- El repositorio público de GitHub (`sebdavid3/Cadenza`) es la prueba que se puede enlazar.
- Debe evitarse que se sienta como una startup SaaS (gradientes, promesas, tono de venta), una intranet académica gris, una app lúdica para aficionados o un pastiche de partitura antigua (pergamino, caligrafía, ornamentos).

## Evidence on Hand

- Código abierto y documentación en `sebdavid3/Cadenza`.
- No existen testimonios, clientes, logos de instituciones ni cifras de rendimiento citables en la página pública. No se inventan.

## Product Principles

1. La persona decide: la máquina propone y señala; nada se presenta como transcripción definitiva.
2. Alcance honesto: solo se promete lo medido.
3. Nada se pierde: cada corrección queda registrada y se puede deshacer.
4. El trabajo por lotes no se bloquea: subir, esperar y revisar conviven sin congelar la interfaz.
