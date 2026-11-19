# ADR-0073: Las cifras de los errores de HOMR, en vivo

- **Estado:** Aceptado
- **Fecha:** 2026-11-19
- **Decisores:** Responsable del proyecto (decidió el 2026-11-19 que la portada enseñe en vivo las cifras de conjunto de las correcciones, sin fotos, y que se despliegue en cuanto esté listo) y Equipo de Desarrollo
- **Revisa:** [ADR-0069](ADR-0069-informe-visual-de-los-errores-de-homr.md) (alternativa «una vista en la web») y la prohibición de [#400](https://github.com/sebdavid3/Cadenza/issues/400) de conectar la exportación a la base de producción
- **Relacionado:** [ADR-0036](ADR-0036-capa-de-sugerencias-aprendida.md) §8, [ADR-0065](ADR-0065-permiso-de-uso-de-los-datos-al-registrarse.md), [ADR-0068](ADR-0068-tablas-y-recortes-en-una-sola-exportacion.md), [#418](https://github.com/sebdavid3/Cadenza/issues/418), [#422](https://github.com/sebdavid3/Cadenza/issues/422), [#423](https://github.com/sebdavid3/Cadenza/issues/423), [#424](https://github.com/sebdavid3/Cadenza/issues/424)

---

## Contexto

El informe local (`ml export-tables --informe`, ADR-0069) calcula de los CSV qué se corrige, la figura leída frente a la correcta y dónde se equivoca más HOMR. Se abre en local y lleva fotos. El responsable quiere esas cifras en la portada (#424), en vivo y sin fotos.

Hay tres límites:

- **El permiso** (ADR-0065) solo deja publicar «cifras de conjunto, nunca con tu nombre de usuario ni con tus partituras de forma que se te pueda reconocer». Si alguien lo retira, sus datos dejan de usarse desde entonces.
- **Los planos online y offline** solo se comunican por datos persistidos (`CLAUDE.md` §10.7). El código de las cifras vive en `ml/` y `cadenza.learning`, que la API no importa ni lleva en su imagen.
- **Producción** está en pruebas con público. El cálculo no puede poner en riesgo la base ni la API.

## Decisión

1. **Un servicio periódico del compose las calcula.** `stats` (`Dockerfile.stats`, imagen `cadenza-stats`) ejecuta `python -m ml.public_stats --every 300`: sin HOMR ni GPU, con `cadenza-learning`, `cadenza-persistence`, `ml/tables_report.py` y `ml/public_stats.py`. Cada vez recalcula todo, no por sesión. Así un permiso retirado sale en el siguiente cálculo, y un fallo se arregla solo en la vuelta siguiente.
   - **Lee la base en solo lectura y sobre una sola foto:** una transacción `REPEATABLE READ, READ ONLY` en PostgreSQL. Con `READ COMMITTED`, cada consulta vería la base de su momento, y una sesión finalizada a mitad del cálculo entraría sin pasar por el filtro del permiso. Escribe en otra transacción, y solo en su tabla.
   - **El código es el del informe:** `database_tables` y `corpus_tables` (`cadenza.learning.tables`), y `aggregate` y `reordered_chords` (`ml/tables_report.py`). Las filas pasan por `cell`, como en los CSV, así que las cifras son las que daría el informe con esas sesiones. `ml/tables_report.py` no cambia.
2. **Dónde se guardan: la tabla `public_stats`** (migración 0019), una fila por grupo. Es el mismo camino que la capa de sugerencias (ADR-0036 §8): el plano offline escribe una tabla y la API la lee. Cada fila lleva `id`, `source` (`cadenza` o `corpus`), `computed_at`, `format_version`, `min_sessions`, `sessions`, `source_sha256` (el del corpus) y `stats` (JSON, nulo si el grupo no se publica). El puerto es `PublicStatsRepository` (`cadenza.application.public_stats`) y el adaptador, `SqlAlchemyPublicStatsRepository`.
3. **Cada cuánto:** cada 5 minutos (`CADENZA_STATS_EVERY_SECONDS`, 300 por defecto); un cálculo fallido se reintenta al minuto. Los corpus (PrIMuS y, cuando llegue, Camera-PrIMuS, #421; MUSCIMA++ y SMB quedaron fuera por decisión del responsable del 2026-11-19) van precalculados: cada `<grupo>.jsonl` de la carpeta montada (`CADENZA_STATS_CORPUS_DIR`) se calcula al arrancar el servicio (en cada despliegue, por si cambió el código) y después solo si cambia su sha256. Sin corpus, no hay grupo de corpus. Un archivo que no se puede leer, o que trae sesiones de Cadenza (un corpus de `build-dataset`, que saltaría el mínimo del §5), se salta con un aviso y no para las cifras en vivo. Las cifras salen de la ejecución sobre el archivo, nunca escritas a mano (`CLAUDE.md` §8).
4. **Qué sesiones cuentan:** las de `session_records` con el criterio de #422. Son las sesiones finalizadas de las cuentas del equipo y de las cuentas del registro con el permiso de la versión vigente del texto. Una cuenta sin permiso vigente nunca entra.
5. **Grupos:**
   - `cadenza`: todas las sesiones que cuentan;
   - `pruebas`: solo las de las cuentas del registro (`origen = registro`, el filtro del informe);
   - uno por corpus (`primus`).

   Un grupo de Cadenza se publica con **al menos 5 sesiones de al menos 3 cuentas** (`MIN_PUBLIC_SESSIONS`, `MIN_PUBLIC_ACCOUNTS`): cinco sesiones de una sola persona serían sus cifras, no unas de conjunto. `pruebas` tampoco se publica si lo que queda de `cadenza` sin ella tiene entre 1 y 4 sesiones, porque restar un grupo del otro daría sus cifras. Por debajo, la fila dice solo que no se publica, sin el recuento de sesiones ni cifras, y la API vuelve a comprobar el mínimo de sesiones de cada fila. Los acordes solo reordenados no se cuentan en ningún grupo (ADR-0069 §5), y se publica cuántos son.
6. **Qué se publica:** solo agregados musicales de cada grupo:
   - partituras y cuántas salieron sin ninguna corrección;
   - notas leídas, qué pasó con ellas (bien, corregida, leída de más, sin alinear) y las que faltaban;
   - las correcciones por tipo y cuánto se movió la altura;
   - la figura leída frente a la correcta, con el nombre y el símbolo de cada figura (`figure_name` y `figure_symbol`);
   - la proporción de notas corregidas por alteración frente a la armadura, por clave y por figura leída, en grupos de 30 notas o más (`MIN_GROUP`).

   **No se publica:** fotos, recortes, compases dibujados, ejemplos, filas por sesión (`per_score`), identificadores de sesión, nombres de cuenta, títulos, páginas del banco ni fechas de las sesiones. La API valida cada fila con su propio esquema y solo devuelve los campos que declara: aunque la tabla llevara algo más, no saldría.
7. **El endpoint:** `GET /stats/homr-errors`, sin autenticación. Devuelve `computed_at` (el último cálculo de Cadenza, nulo si aún no lo hay) y los grupos con su hora, su mínimo, si se publican y sus cifras. Lleva `Cache-Control: public, max-age=60`, `ETag` y `304` con `If-None-Match`, y una caché en el proceso de 60 s (`CADENZA_STATS_CACHE_SECONDS`), así que las visitas a la portada no llegan a la base. Una fila con otro `format_version` o que no valida no se publica y se anota en el registro. Es una ampliación compatible del contrato v1.

## Consecuencias

### Positivas
- La web enseña los errores de HOMR con unos minutos de retraso (los 5 del ciclo, lo que tarda el cálculo, las cachés de 60 s de la API y del navegador y, con la página abierta, hasta 5 más hasta que la vuelve a pedir), con el mismo código que el informe local.
- La API no importa `ml/` ni `cadenza.learning` y no calcula nada: lee una tabla pequeña.
- Retirar el permiso tiene efecto en el siguiente cálculo, sin código aparte.

### Negativas / Riesgos
- **Recalcular todo cuesta** una pasada por todas las sesiones finalizadas cada 5 minutos, con su materialización, y las tablas de todas en memoria (`database_tables` no va por partes). Con cientos de sesiones son segundos y cientos de MiB; el corpus de PrIMuS (1877 íncipits) llega a unos 330 MiB al calcularse. El servicio tiene un tope de 1 GiB: si la base crece hasta pasarlo, el contenedor muere y se reinicia sin tocar la API, y se sube el tope o `CADENZA_STATS_EVERY_SECONDS`, o se para el servicio, sin código.
- **Comparar dos cálculos seguidos** puede aislar la contribución de una sesión, si solo una se finalizó entre ellos. Lo que se aísla son cifras musicales (cuántas notas se corrigieron y de qué tipo), sin cuenta, título ni foto. Se acepta. La resta entre los dos grupos de un mismo cálculo la impide el §5.
- **El servicio escribe en la base** de producción, aunque solo en `public_stats`, con las mismas credenciales que la API: el compose no tiene otro usuario de PostgreSQL. La lectura sí va en solo lectura.
- **Una imagen más que construir** en cada despliegue (`docker compose up -d --build`), ligera y sin GPU.

## Alternativas consideradas
- **Calcular al finalizar cada sesión.** La API tendría que agregar con el código del plano offline, en contra de §10.7 y de su imagen, y retirar un permiso obligaría a recalcularlo todo igual.
- **Un artefacto JSON en un volumen compartido.** Dejaría la base del todo en solo lectura, pero el volumen tendría que crearlo con el dueño correcto la primera imagen que lo monte, y la API tendría que leer un archivo fuera de su almacén. La tabla sigue el camino de ADR-0036 y entra en las copias.
- **Calcular en la API al pedirlo, con caché.** Lleva el cálculo y `ml/` al plano online, y una visita puede disparar una pasada por toda la base.
- **Un umbral por celda** (cada barra o casilla con 5 sesiones o más). Vaciaría la matriz de figuras con pocas sesiones, y una celda solo dice cuántas veces HOMR leyó una figura por otra. El mínimo va por grupo.

## Enmienda de #424 (2026-11-19): las cifras, en su propia página

El responsable decidió, mientras se hacía #424, que las cifras no vayan en la portada sino en una vista propia. Es pública y se enlaza desde la cabecera: `/errores-de-homr`. Donde este ADR dice «la portada», se lee esa página. Lo demás no cambia: qué se calcula, cada cuánto, qué se publica y el endpoint.

## Enmienda de #424 (2026-11-19): los ejemplos de los corpus

El responsable decidió que la vista en vivo sea el informe local (#418) en línea, y que de PrIMuS y Camera-PrIMuS enseñe también los ejemplos con su compás dibujado.

- **Solo los grupos de corpus** llevan los ejemplos: `examples`, `example_keys` y `bars` en sus `stats`. Los calcula `ml/public_stats.py` con el mismo `aggregate` y los mismos compases dibujados (`_Bars`) del informe. No llevan ni el recorte (`img`) ni los ejemplos de cada partitura (`score:`, el historial).
- **Los grupos de Cadenza** (`cadenza` y `pruebas`) siguen sin ejemplos, sin historial y sin nada por partitura. La API los quita de una fila de Cadenza aunque los trajera.
- **La web dibuja cada compás desde los datos**, como el informe (`staffSvg`, `groupSvg`, `barHtml`), y cita el corpus. La enmienda siguiente añade sus imágenes.
- **El formato pasa a la 2** (`PUBLIC_STATS_FORMAT_VERSION`). Al desplegar, las filas de la 1 no se publican hasta el siguiente cálculo, que el servicio hace al arrancar, con los corpus recalculados. Es una ampliación compatible del contrato: los tres campos son opcionales y nulos en Cadenza.
- **Lo que pesa:** con el corpus de PrIMuS de `exp_12` son 612 ejemplos, 111 cifras y 392 compases, unos 390 KiB de JSON por corpus, que Nginx sirve comprimidos y la caché de 60 s ahorra.

## Enmienda de #424 (2026-11-19): el historial de los corpus y sus imágenes

El responsable pidió el historial de transcripciones del informe local y, al ver la página, la imagen de cada partitura junto a sus correcciones, como en el informe.

- **El historial, solo de los corpus.** Cada grupo de corpus lleva en `stats.history` una fila por partitura: su íncipit, su nombre, sus notas leídas, sus correcciones y si tiene imagen. Las de Cadenza no tienen historial ni detalle: el permiso de uso de los datos (ADR-0065) solo deja publicar cifras de conjunto, nunca nada de una transcripción concreta. La API quita `history` de una fila de Cadenza aunque lo trajera, y la página lo explica.
- **El detalle de cada partitura, aparte.** Sus ejemplos (los del informe, hasta 12) con su compás dibujado irían a la respuesta principal con unos 3 MB por corpus. Por eso van en una tabla propia, `public_stats_scores` (migración 0020), una fila por partitura, sin clave foránea: el servicio `stats` la escribe solo para los corpus que recalcula y borra la de los que ya no están. `GET /stats/homr-errors/{grupo}/scores/{íncipit}` la sirve al elegir la partitura (unos 5 KB), con `ETag` y 404 si no está o es de un grupo de Cadenza.
- **Las imágenes de PrIMuS y Camera-PrIMuS.** Decisión del responsable del 2026-11-19, que revisa la del punto anterior («nunca sus imágenes»): se publican aunque la página del corpus no indique licencia, citándolo. Cada ejemplo enseña encima de su compás dibujado la imagen de su íncipit, la de PrIMuS o la distorsionada de Camera-PrIMuS. El servicio las toma de `<grupo>/<íncipit>.png` (o `.jpg`) junto al archivo del corpus. Solo acepta un PNG o un JPEG de verdad de hasta 1 MB. Las guarda en la fila de su partitura (columnas `image` e `image_type`; unos 4 MB los de PrIMuS y 47 MB los de Camera-PrIMuS). `GET .../scores/{íncipit}/image` las sirve. Nunca se publica una ruta, y la API no lee archivos. `ml public-stats-images` copia las imágenes desde las descargas de los corpus.
- **El formato pasa a la 3.** Al desplegar, el servicio recalcula los corpus al arrancar, con sus imágenes si ya están en la carpeta; las que se añadan después entran en el siguiente arranque. Es una ampliación compatible del contrato: `history` es opcional y nulo en Cadenza, y hay dos rutas nuevas.
