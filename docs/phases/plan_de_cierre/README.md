# Plan de cierre del proyecto (26 de octubre – 15 de noviembre de 2026)

**Objetivo:** terminar Cadenza en tres semanas, con tres personas, con un alcance acordado y
unos límites explícitos. Acordado con el responsable el 2026-10-25.

Seguimiento en GitHub: [#231](https://github.com/sebdavid3/Cadenza/issues/231), con la lista
de issues por semana y carril. Milestones:
[Fase 8](https://github.com/sebdavid3/Cadenza/milestone/3),
[Fase 9](https://github.com/sebdavid3/Cadenza/milestone/5),
[Fase 10](https://github.com/sebdavid3/Cadenza/milestone/6),
[Fase 11](https://github.com/sebdavid3/Cadenza/milestone/7),
[Cierre del proyecto](https://github.com/sebdavid3/Cadenza/milestone/8) y
[Trabajo futuro](https://github.com/sebdavid3/Cadenza/milestone/9).

---

## Resultado final (definición de terminado)

Al 15 de noviembre de 2026:

1. **Transcribir.** Una persona sube una página impresa (una línea, piano, o una voz o un
   instrumento superior con piano), también desde la portada ([#277](https://github.com/sebdavid3/Cadenza/issues/277)), indica el título
   (que es el nombre de la sesión), el compositor y los instrumentos, y
   Cadenza la transcribe con HOMR y una etapa propia que reconoce el compás (numerador por
   tramos, C y ¢) y los tresillos implícitos. Los cambios de armadura quedan medidos, y
   corregidos si fallan.
2. **Revisar y corregir.** Las reglas hablan en lenguaje musical. Se corrigen la altura, la
   figura, la alteración, el compás, los tresillos, los acordes, la clave, la armadura y las
   marcas (los matices, a mano); se insertan y borran eventos, se deshace y se rehace, y se
   descartan los posibles errores. Cada edición responde en un solo viaje, sin parpadeos ni órdenes perdidas
   ([#275](https://github.com/sebdavid3/Cadenza/issues/275), [#276](https://github.com/sebdavid3/Cadenza/issues/276)).
3. **Cerrar y exportar.** Se finaliza y se reabre; se exporta a MusicXML y MIDI con el título y
   los instrumentos; cada parte suena con su instrumento.
4. **Estudio.** El estudio de esfuerzo con 8 participantes (D38,
   [`protocolo_medicion_esfuerzo.md`](../../experimentos/protocolo_medicion_esfuerzo.md)) hecho
   con el sistema congelado el 8 de noviembre, exportado y analizado: tiempos, intervenciones,
   NASA-TLX y fidelidad residual.
5. **Aprender de las correcciones: el estandarte.** Una capa entrenada con correcciones
   (derivadas de PrIMuS y las hechas en Cadenza) sugiere el arreglo de cada posible error y
   señala errores que las reglas no ven. La persona ve la sugerencia, la aplica con un clic o la
   rechaza, y su respuesta alimenta el siguiente entrenamiento. Medida con validación cruzada y
   curva de aprendizaje, mejore o no. No reentrena HOMR.
6. **Entregar.** Todo medido y documentado, con la licencia resuelta, desplegado y con `dev`
   promovido a `main`.

## Límites: fuera de esta entrega

| Fuera | Por qué | Issue |
|---|---|---|
| Matices reconocidos automáticamente (Audiveris) | HOMR 0.7.0 no los reconoce; Audiveris acierta poco en las dinámicas sin OCR y tarda 35–51 s por página real en CPU, 75 s un autógrafo ([INV-0002](../../investigaciones/INV-0002-audiveris-frente-a-homr.md)). Los matices se ponen a mano | [#262](https://github.com/sebdavid3/Cadenza/issues/262); a mano, [#214](https://github.com/sebdavid3/Cadenza/issues/214) |
| Reintento con preprocesado y HOMR en la GPU de producción | Recortados el 2026-10-27 por el responsable: es el único punto que se aplica del orden de recorte (#272). El estudio se hace con HOMR en CPU, y [#269](https://github.com/sebdavid3/Cadenza/issues/269) mide la latencia de las páginas completas y fija el tamaño máximo de página | [#267](https://github.com/sebdavid3/Cadenza/issues/267), [#268](https://github.com/sebdavid3/Cadenza/issues/268) |
| Cambiar de motor (Transcoda) | Una prueba exploratoria del 2026-10-26, no citable, salió peor que HOMR en nuestras páginas: en *Mondnacht* entra en bucles y lee mal el compás, y en 10 incipits de PrIMuS (líneas sueltas, fuera de su tipo de entrada) también queda por detrás. Queda como trabajo futuro con ajuste fino | [#273](https://github.com/sebdavid3/Cadenza/issues/273) |
| Reentrenar HOMR (D14) y la imagen del plano offline (D53) | Necesita el código de entrenamiento de HOMR, GPU y muchos más datos que las 32 sesiones del estudio (8 participantes por 4 partituras); no cabe en el plazo. «Aprender de las correcciones» se cubre con la capa de [#256](https://github.com/sebdavid3/Cadenza/issues/256) | [#103](https://github.com/sebdavid3/Cadenza/issues/103) |
| Evaluar sobre SMB y MUSCIMA++ (D34) | Plazo | [#102](https://github.com/sebdavid3/Cadenza/issues/102) |
| Título y letra leídos de la imagen | El OCR del título de HOMR alargaba la latencia (#106) y HOMR no lee la letra. El título y el compositor se escriben en un formulario ([#240](https://github.com/sebdavid3/Cadenza/issues/240)) | [#263](https://github.com/sebdavid3/Cadenza/issues/263) |
| Volumen de la reproducción según los matices | Sin matices reconocidos, solo afectaría a los puestos a mano | [#215](https://github.com/sebdavid3/Cadenza/issues/215) |
| Políticas completas del registro abierto (D59) | Para el estudio basta cerrar el registro ([#248](https://github.com/sebdavid3/Cadenza/issues/248)) | [#194](https://github.com/sebdavid3/Cadenza/issues/194) |
| D62 y D64 | No bloquean el estudio si el banco de partituras evita D62 | [#264](https://github.com/sebdavid3/Cadenza/issues/264) |
| PDF y varias páginas; marcas sobre la imagen original | Ya fuera antes ([#38](https://github.com/sebdavid3/Cadenza/issues/38), INV-0001) | — |

## Calendario

| Semana | Fechas | Qué |
|---|---|---|
| 1 | 26 oct – 1 nov | Construir |
| 2 | 2 – 8 nov | Completar; piloto el 6 y 7; **congelado el 8** ([#252](https://github.com/sebdavid3/Cadenza/issues/252)) |
| 3 | 9 – 15 nov | Estudio, aprendizaje y cierre |

El estudio se hace con el sistema congelado: lo que no esté desplegado el 8 de noviembre no
entra, y entre el 9 y el 15 no se despliega nada salvo un arreglo que bloquee el estudio, con
decisión del responsable. Lo que se fusione después del congelado se despliega al acabar el
estudio ([#261](https://github.com/sebdavid3/Cadenza/issues/261)).

## Carriles

Una persona por carril, cada una con sus carpetas principales, para que los PR choquen lo menos posible:

| Carril | Etiqueta | Carpetas |
|---|---|---|
| A · Reconocimiento y aprendizaje | `carril A: reconocimiento` | `packages/omr`, `packages/interchange`, `packages/domain`, `packages/learning` |
| B · Web | `carril B: web` | `apps/web` y la parte de API de sus issues |
| C · Reglas y estudio | `carril C: reglas y estudio` | `packages/validation`, `ml/experiments`, `docs/experimentos` |

Algunos issues cruzan carpetas: #235 y #243 tocan el dominio; #236 y #248, la API; #239, #248 y #269 (si cambia lo que admite la web), la web; #250 usa las métricas de `packages/learning`, y #271 toca su entrenador, en coordinación con #256; #275 toca `packages/interchange`, `packages/application` y `deploy/nginx`; #256, `packages/validation` y la API; y #278, `packages/persistence`. Quien los hace avisa antes al carril dueño de la carpeta.

## Orden de los issues

Cada carril trabaja en el orden de sus códigos (A1, A2…; B1, B2…; C1, C2…; R1… para el
responsable; T1 para todos). «Tras X» marca una dependencia. #234, #256 y #257 tienen varias
etapas, con un código cada una. Las casillas están en [#231](https://github.com/sebdavid3/Cadenza/issues/231), y cada issue lleva el suyo en
la sección «Plan». Hechos: #232 (este plan) y #233 (INV-0002). A8 (#267) y R5 (#268) se
recortaron el 27 de octubre (#272).

| Semana | Carril A | Carril B | Carril C | Responsable y todos |
|---|---|---|---|---|
| 1 | **A1** [#234](https://github.com/sebdavid3/Cadenza/issues/234) conjunto de referencia (tras R1; desbloquea A5, A9 y A10)<br>**A2** [#255](https://github.com/sebdavid3/Cadenza/issues/255) corpus de correcciones (**estandarte**: el cálculo corre mientras se escribe A3)<br>**A3** [#256](https://github.com/sebdavid3/Cadenza/issues/256) capa de sugerencias: el ADR (**estandarte**)<br>**A4** [#236](https://github.com/sebdavid3/Cadenza/issues/236) compás y tresillos en el dominio (tras B1 y B3) | **B1** [#214](https://github.com/sebdavid3/Cadenza/issues/214) añadir y quitar marcas (primero en la cola del contrato; desbloquea A4)<br>**B2** [#187](https://github.com/sebdavid3/Cadenza/issues/187) finalizar y reabrir, con D65 (lo necesita el piloto; desbloquea B6)<br>**B3** [#235](https://github.com/sebdavid3/Cadenza/issues/235) título, compositor e instrumentos (desbloquea A4, A10, B8 y B11)<br>**B4** [#275](https://github.com/sebdavid3/Cadenza/issues/275) una edición en un solo viaje (**prioridad alta**; con apoyo de A en la API; sigue en la semana 2) | **C1** [#244](https://github.com/sebdavid3/Cadenza/issues/244) definiciones del protocolo (las decide el responsable; desbloquea B6, C4 y C7)<br>**C2** [#245](https://github.com/sebdavid3/Cadenza/issues/245) ADR de reglas y mensajes (**prioridad alta**: los primeros días)<br>**C3** [#248](https://github.com/sebdavid3/Cadenza/issues/248) cerrar el registro durante el estudio<br>**C4** [#247](https://github.com/sebdavid3/Cadenza/issues/247) banco de partituras: elegirlo (se comprueba en la semana 2)<br>**C5** [#226](https://github.com/sebdavid3/Cadenza/issues/226) tiempo de respuesta del login | **R1** [#234](https://github.com/sebdavid3/Cadenza/issues/234) permiso para las descargas de corpus y páginas de A1 (día 1)<br>**R2** [#272](https://github.com/sebdavid3/Cadenza/issues/272) orden de recorte: decidido el 27 oct (solo el punto 7: #267 y #268 pasan a «Trabajo futuro»)<br>**R3** [#270](https://github.com/sebdavid3/Cadenza/issues/270) objetivos de la tesis: la decisión con el director (el texto, con T1)<br>**R4** [#259](https://github.com/sebdavid3/Cadenza/issues/259) licencia: la decisión (se aplica en la semana 3) |
| 2 | **A5** [#237](https://github.com/sebdavid3/Cadenza/issues/237) reconocer compás y tresillos (**prioridad alta**; tras A1 y A4; lo necesita el piloto)<br>**A6** [#256](https://github.com/sebdavid3/Cadenza/issues/256) capa de sugerencias: implementación (**estandarte**; tras A2, C2 y C6: empieza sobre las reglas actuales y se rebasa cuando llegue C6)<br>**A7** [#257](https://github.com/sebdavid3/Cadenza/issues/257) primera medición de la capa (**estandarte**: hasta el 5 nov; tras A6)<br>**A9** [#238](https://github.com/sebdavid3/Cadenza/issues/238) cambios de armadura (tras A1; si no llega, después del estudio)<br>**A10** [#239](https://github.com/sebdavid3/Cadenza/issues/239) voz y piano (tras A1 y B3; va antes de A7 si C1 elige un TS-04 de voz y piano) | **B5** [#276](https://github.com/sebdavid3/Cadenza/issues/276) redibujar sin parpadeos (**prioridad alta**; tras B4)<br>**B6** [#188](https://github.com/sebdavid3/Cadenza/issues/188) métricas de esfuerzo (tras B2 y C1; lo necesita el piloto)<br>**B7** [#241](https://github.com/sebdavid3/Cadenza/issues/241) compás y tresillos en la barra (tras A4; lo necesita el piloto)<br>**B8** [#240](https://github.com/sebdavid3/Cadenza/issues/240) nombre e instrumento antes de transcribir (tras B3; lo pide el piloto, salvo que R2 lo recorte)<br>**B9** [#258](https://github.com/sebdavid3/Cadenza/issues/258) ver, aplicar y rechazar las sugerencias (**estandarte**: se construye con el contrato de A3 y se fusiona tras A6; antes del piloto si el estudio usa la capa)<br>**B10** [#243](https://github.com/sebdavid3/Cadenza/issues/243) figura de un acorde, D61 (va antes si C1 elige un TS-04 de piano con acordes)<br>**B11** [#242](https://github.com/sebdavid3/Cadenza/issues/242) sonido por instrumento (tras B3) | **C6** [#246](https://github.com/sebdavid3/Cadenza/issues/246) implementar las reglas y medir de nuevo exp_06 (tras C2 y A4; hasta el 3 nov, porque A6 lo necesita)<br>**C7** [#250](https://github.com/sebdavid3/Cadenza/issues/250) fidelidad residual y NASA-TLX (tras C1 y C4)<br>**C8** [#249](https://github.com/sebdavid3/Cadenza/issues/249) cuentas y sesiones de cada participante (tras C3 y C4)<br>**C9** [#269](https://github.com/sebdavid3/Cadenza/issues/269) latencia y tamaño máximo de página, con HOMR en CPU (#268 se recortó)<br>**C10** [#251](https://github.com/sebdavid3/Cadenza/issues/251) piloto, 6 y 7 de noviembre | **R6** [#252](https://github.com/sebdavid3/Cadenza/issues/252) congelado del sistema (8 nov) |
| 3 | **A11** [#256](https://github.com/sebdavid3/Cadenza/issues/256) reentrenar la capa con las sesiones del estudio (cierra #256)<br>**A12** [#257](https://github.com/sebdavid3/Cadenza/issues/257) medición final con la curva de aprendizaje (cierra #257) | **B12** [#277](https://github.com/sebdavid3/Cadenza/issues/277) subir y ver la transcripción desde la portada (tras B8; no afecta al estudio)<br>**B13** [#189](https://github.com/sebdavid3/Cadenza/issues/189) descargar el MIDI<br>**B14** [#190](https://github.com/sebdavid3/Cadenza/issues/190) cambiar la contraseña<br>**B15** [#278](https://github.com/sebdavid3/Cadenza/issues/278) transcribir sin cuenta (tras B12; se despliega después del estudio) | **C11** [#253](https://github.com/sebdavid3/Cadenza/issues/253) sesiones con participantes, del 9 al 15 de noviembre (con apoyo de A y B)<br>**C12** [#254](https://github.com/sebdavid3/Cadenza/issues/254) exportación y análisis, del 13 al 15 de noviembre<br>**C13** [#271](https://github.com/sebdavid3/Cadenza/issues/271) retirar o marcar lo simulado (en coordinación con A11) | **R7** [#261](https://github.com/sebdavid3/Cadenza/issues/261) despliegue final y `dev` → `main` (15 nov; tras C11 y T1)<br>**T1** [#260](https://github.com/sebdavid3/Cadenza/issues/260) documentación final y límites |

**Puntos de control** (decididos el 27 oct, R2): 30 oct, ADR de reglas (C2) y protocolo (C1);
3 nov, reglas nuevas (C6); 4 nov, todo lo que entra en el congelado, en revisión o fusionado;
5 nov, primera medición de la capa (A7), con la que el responsable decide si entra en el
estudio; 7 nov, el piloto (C10) sin bloqueos.

## Reglas de coordinación

- **Contrato de la API.** Los PR que regeneran `openapi.json` y `types.ts` se fusionan de uno
  en uno, en este orden: #214 (B1) → #235 (B3) → #275 (B4) → #236 (A4) → #256 (A6) → #258 (B9) →
  #243 (B10, si cambia el contrato) → #278 (B15). Cada uno se
  rebasa sobre `dev` y regenera con `scripts/generate_openapi_and_types.py` antes de fusionar. Si otro PR necesita regenerar el contrato (por ejemplo #246 o #248), se avisa en #231 y entra en la misma cola, de uno en uno. Un PR que no esté listo cede su turno al siguiente: la cola fija el orden de fusión, no espera a nadie.
- **`EditOp`.** Las operaciones nuevas siguen la política que fije el ADR de #214 para el
  dataset y las métricas (`alignment.py`, la cobertura de `exp_02` con `len(EditOp)` y
  `test_edit_event.py`); las cifras de `results/` no cambian.
- **Experimentos.** La etapa de reconocimiento nueva (#237) y la capa aprendida (#256) van
  fuera de `HOMREngine`: `exp_04`, `exp_07` y `exp_11` siguen midiendo HOMR solo, y cada mejora
  se mide con su propio experimento.
- **Flujo por issue:** el de `CLAUDE.md` §4, sin excepciones.

## Criterio de cierre

1. Los seis puntos del resultado final, con evidencia.
2. Los issues de las Fases 8 a 11 y de «Cierre del proyecto» cerrados, salvo los que el orden
   de recorte (#272) pase a «Trabajo futuro». Los de «Trabajo futuro», abiertos con la
   etiqueta `fuera de alcance` y citados como límites en la documentación final.
3. Las puertas de `CLAUDE.md` §6 en verde, y `dev` promovido a `main` por el responsable.
