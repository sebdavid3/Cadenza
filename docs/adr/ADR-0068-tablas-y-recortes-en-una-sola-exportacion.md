# ADR-0068: Las tablas y los recortes de las fotos en una sola exportación

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decisores:** Responsable del proyecto (pidió el 2026-11-12 unir las dos exportaciones porque las fotos son importantes) y Equipo de Desarrollo
- **Relacionado:** [ADR-0065](ADR-0065-permiso-de-uso-de-los-datos-al-registrarse.md), [ADR-0067](ADR-0067-captura-de-homr-y-recortes-de-los-pentagramas.md), [#400](https://github.com/sebdavid3/Cadenza/issues/400), [#403](https://github.com/sebdavid3/Cadenza/issues/403), [#414](https://github.com/sebdavid3/Cadenza/issues/414)

---

## Contexto

La toma de datos tenía dos exportaciones que no se conocían:

- `ml export-tables` (#400): CSV planos con cada nota leída, su corrección y su contexto, para reconocer los errores de HOMR.
- `ml export-staves` (#403, ADR-0067): cada pentagrama de la foto recortado y emparejado con lo que leyó HOMR y lo corregido (`pentagramas.csv`).

Las dos hablan de lo mismo (sesión, parte, pentagrama, compás), pero desde una fila de las tablas no se llegaba a su foto, y cada comando filtraba las sesiones por su cuenta. Una prueba del 2026-11-12 sobre `TS-04` transcrita con HOMR unió los 18 compases de `compases.csv` con su tira de `pentagramas.csv` por sesión, `parte-pentagrama` y número de compás. Los incipits de PrIMuS traen su imagen (`<paquete>/<id>/<id>.png`).

## Decisión

1. **Una opción, no un comando nuevo.** `ml export-tables --recortes` escribe, en la misma carpeta, lo que escribe `ml export-staves` (`recortes/`, `musicxml/`, `pentagramas.csv` y, con `--laminas`, `laminas/`) **para las sesiones que están en las tablas**: un solo filtro (el de `session_records`, con el permiso de uso de los datos vigente para las cuentas del registro, enmienda de #400 en ADR-0065). Las fotos salen de `--artifacts-dir` o `CADENZA_ARTIFACTS_DIR`. Por dentro es el mismo código: `export_session_strips` y `strips_csv` de `ml/export_staves_cli.py`, así que `pentagramas.csv` sale igual byte a byte. `ml export-staves` sigue funcionando igual.
2. **Dos columnas unen las tablas y las fotos.** `notas`, `faltantes` y `compases` terminan en `sistema` y `recorte` (la ruta relativa del PNG de la tira). Se unen por sesión, parte, pentagrama y número de compás: un gran pentagrama de piano da su tira a sus dos pentagramas. Están siempre en la cabecera y vacías sin `--recortes`, o si la sesión no tiene recortes (sin captura, o cuyas cajas no casan): esa sesión sigue en las tablas y el motivo queda en `run_info.json`.
3. **PrIMuS también lleva su imagen.** Con `--primus-dir` (la carpeta de `data/primus`, que solo se lee), la imagen de cada incipit de las tablas se copia a `recortes/primus/<id>.png` y va en `recorte`, con `sistema` 1. Las que faltan se listan.
4. **`run_info.json` gana `recortes`** (sesiones con recortes, las que no y por qué, tiras, tiras corregidas, sha256 de `pentagramas.csv`, láminas, imágenes de PrIMuS copiadas y las que faltan) y pasa a `format_version` 2.
5. **La salida, como en `export-staves`:** ha de estar vacía (lo de una exportación anterior, quizá de alguien que ya retiró su permiso, se quedaría) y no puede caer en `results/` ni en `data/` del repositorio. Vale también sin `--recortes`.

## Consecuencias

### Positivas
- Desde cualquier fila de `notas` o `compases` se llega a su foto en pandas o en una hoja de cálculo; es la base del informe visual de #415.
- Las tablas y las fotos son siempre de las mismas sesiones y con la misma regla de permiso.
- Probado el 2026-11-12 sobre `TS-04` y el corpus de `exp_12`: 6 tiras, las 1 877 imágenes de PrIMuS, cada compás con su tira, en 20 s.

### Negativas / Riesgos
- Con las fotos, la carpeta de salida tiene imágenes de personas: se trata como los datos que son (ADR-0065) y no se comparte sin su permiso.
- La unión usa el número de compás, como las demás uniones por compás de las tablas: si una lectura repitiera un número en un pentagrama, esos compases compartirían tira.
- Una imagen de PrIMuS es el incipit entero: su `recorte` no es una tira por sistema.
- Los recortes se escriben antes que las tablas: si la exportación se corta a medias (un error de la base o de disco), quedan fotos sin `run_info.json`, y la siguiente pide una carpeta vacía. Como en `export-staves`.
- `results/` y `data/` se protegen en la copia del repositorio desde la que corre `ml` (resueltas, por si son un enlace o una unión); desde un worktree, no las de la carpeta principal.
- `ml export-staves` cambia solo el texto de un motivo de `left_out`, a «cuenta del registro sin el permiso de uso de los datos vigente», el mismo que las tablas.

## Alternativas consideradas
- **Un comando nuevo que llamara a los dos.** Dos filtros que mantener a la par y dos `run_info.json`; se descartó.
- **Meter las tablas en `export-staves`.** `export-staves` es de la base; las tablas leen también el corpus de PrIMuS.
- **Una tabla de unión aparte.** Obligaría a unir siempre tres tablas para ver una foto; dos columnas bastan.
