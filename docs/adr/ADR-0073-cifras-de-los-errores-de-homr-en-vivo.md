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
   - **Lee la base en solo lectura:** una transacción `READ ONLY` en PostgreSQL. Escribe en otra transacción, y solo en su tabla.
   - **El código es el del informe:** `database_tables` y `corpus_tables` (`cadenza.learning.tables`), y `aggregate` y `reordered_chords` (`ml/tables_report.py`). Las filas pasan por `cell`, como en los CSV, así que las cifras son las que daría el informe con esas sesiones. `ml/tables_report.py` no cambia.
2. **Dónde se guardan: la tabla `public_stats`** (migración 0019), una fila por grupo. Es el mismo camino que la capa de sugerencias (ADR-0036 §8): el plano offline escribe una tabla y la API la lee. Cada fila lleva `id`, `source` (`cadenza` o `corpus`), `computed_at`, `format_version`, `min_sessions`, `sessions`, `source_sha256` (el del corpus) y `stats` (JSON, nulo si el grupo no se publica). El puerto es `PublicStatsRepository` (`cadenza.application.public_stats`) y el adaptador, `SqlAlchemyPublicStatsRepository`.
3. **Cada cuánto:** cada 5 minutos (`CADENZA_STATS_EVERY_SECONDS`, 300 por defecto). Los corpus (PrIMuS y, cuando lleguen, Camera-PrIMuS, MUSCIMA++ y SMB) van precalculados: cada `<grupo>.jsonl` de la carpeta montada (`CADENZA_STATS_CORPUS_DIR`) se calcula una vez y solo se repite si cambian su sha256 o el formato. Sin corpus, no hay grupo de corpus. Las cifras salen de la ejecución sobre el archivo, nunca escritas a mano (`CLAUDE.md` §8).
4. **Qué sesiones cuentan:** las de `session_records` con el criterio de #422. Son las sesiones finalizadas de las cuentas del equipo y de las cuentas del registro con el permiso de la versión vigente del texto. Una cuenta sin permiso vigente nunca entra.
5. **Grupos:**
   - `cadenza`: todas las sesiones que cuentan;
   - `pruebas`: solo las de las cuentas del registro (`origen = registro`, el filtro del informe);
   - uno por corpus (`primus`).

   Un grupo de Cadenza se publica con **al menos 5 sesiones** (`MIN_SESSIONS`). Por debajo, la fila dice solo que no se publica, sin el recuento de sesiones ni cifras. Los acordes solo reordenados no se cuentan en ningún grupo (ADR-0069 §5), y se publica cuántos son.
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
- La portada enseña los errores de HOMR con 5 minutos de retraso como mucho, con el mismo código que el informe local.
- La API no importa `ml/` ni `cadenza.learning` y no calcula nada: lee una tabla pequeña.
- Retirar el permiso tiene efecto en el siguiente cálculo, sin código aparte.

### Negativas / Riesgos
- **Recalcular todo cuesta** una pasada por todas las sesiones finalizadas cada 5 minutos, con su materialización. Con cientos de sesiones son segundos. Si crece, se sube `CADENZA_STATS_EVERY_SECONDS`, sin código.
- **Comparar dos cálculos seguidos** puede aislar la contribución de una sesión, si solo una se finalizó entre ellos. Lo que se aísla son cifras musicales (cuántas notas se corrigieron y de qué tipo), sin cuenta, título ni foto. Se acepta.
- **El servicio escribe en la base** de producción, aunque solo en `public_stats`, con las mismas credenciales que la API: el compose no tiene otro usuario de PostgreSQL. La lectura sí va en solo lectura.
- **Una imagen más que construir** en cada despliegue (`docker compose up -d --build`), ligera y sin GPU.

## Alternativas consideradas
- **Calcular al finalizar cada sesión.** La API tendría que agregar con el código del plano offline, en contra de §10.7 y de su imagen, y retirar un permiso obligaría a recalcularlo todo igual.
- **Un artefacto JSON en un volumen compartido.** Dejaría la base del todo en solo lectura, pero el volumen tendría que crearlo con el dueño correcto la primera imagen que lo monte, y la API tendría que leer un archivo fuera de su almacén. La tabla sigue el camino de ADR-0036 y entra en las copias.
- **Calcular en la API al pedirlo, con caché.** Lleva el cálculo y `ml/` al plano online, y una visita puede disparar una pasada por toda la base.
- **Un umbral por celda** (cada barra o casilla con 5 sesiones o más). Vaciaría la matriz de figuras con pocas sesiones, y una celda solo dice cuántas veces HOMR leyó una figura por otra. El mínimo va por grupo.
