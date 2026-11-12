# ADR-0069: El informe visual de los errores de HOMR

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decisores:** Responsable del proyecto (pidió el 2026-11-12 una forma de ver los datos de la toma sin abrir pandas ni una hoja de cálculo) y Equipo de Desarrollo
- **Relacionado:** [ADR-0068](ADR-0068-tablas-y-recortes-en-una-sola-exportacion.md), [#400](https://github.com/sebdavid3/Cadenza/issues/400), [#414](https://github.com/sebdavid3/Cadenza/issues/414), [#415](https://github.com/sebdavid3/Cadenza/issues/415)

---

## Contexto

`ml export-tables` escribe CSV para analizar los errores de HOMR fuera de la plataforma, y con `--recortes` cada compás lleva su foto (ADR-0068). Leer esos CSV exige pandas, R o una hoja de cálculo, y en ellos no se ve la foto. Un prototipo del 2026-11-12 sobre `TS-04` y el corpus de `exp_12` enseñó cosas que no se veían en los CSV:

- HOMR falla sobre todo la figura (10 correcciones por cada 100 notas);
- falla el 50 % de las fusas y semifusas;
- falla el 36 % de las notas con una alteración contra la armadura, frente al 16 % de las que van según la armadura;
- en una partitura comparada con su referencia, 66 de las 76 correcciones de altura de `TS-04` solo reordenaban las notas de un acorde.

## Decisión

1. **Un archivo, sin red.** `ml export-tables --informe` escribe `informe.html` en la carpeta de la exportación (`ml/tables_report.py` y la plantilla `ml/informe_tablas.html`). La página lleva dentro los datos agregados y abre los recortes por su ruta relativa: no carga nada de fuera ni manda nada fuera. Se abre en local, y sus fotos son las de la exportación (ADR-0065).
2. **Sale de los CSV ya escritos.** El informe lee `partituras`, `notas`, `faltantes` y `clave_armadura` de la carpeta, así que sus cifras coinciden con ellos. Una prueba lo comprueba.
3. **Qué enseña:**
   - las cifras de cabecera;
   - qué pasó con cada nota leída, por origen;
   - qué se corrige, por cada 100 notas leídas;
   - cuánto se movió la altura, en pasos de pentagrama;
   - la figura leída frente a la correcta;
   - dónde se equivoca más (alteración frente a la armadura, clave y figura leída, en grupos de 30 notas o más);
   - las partituras con más correcciones.
4. **De cada cifra a sus ejemplos.** Cada barra, celda o fila lleva a hasta 12 ejemplos. Cada ejemplo da la tira de la foto de su compás (`recorte`), la partitura, el compás y el pentagrama, y lo que leyó HOMR frente a lo correcto. Sin `--recortes`, los ejemplos salen sin foto.
5. **Acordes solo reordenados.** Al comparar con una partitura de referencia, un acorde que HOMR escribe en otro orden cuenta como correcciones de altura. Se marcan (`reordered_chords`) y una casilla deja de contarlos. Las correcciones de una persona no tienen este problema.
6. **Filtro por origen** (todos, Cadenza o PrIMuS), modo oscuro, tooltips y una presentación que se lee en un móvil. Los colores de categoría son la paleta validada de la guía de visualización.

## Consecuencias

### Positivas
- Cualquiera del equipo ve los errores de HOMR y sus fotos con un doble clic, sin instalar nada.
- Lo que dice el informe es lo que dicen los CSV.

### Negativas / Riesgos
- Con el corpus de `exp_12`, la página pesa unos 3 MB: los agregados y los ejemplos de seis variantes (tres orígenes, con y sin acordes reordenados).
- La tira es la del sistema entero: el ejemplo dice qué compás mirar, pero no lo recuadra, porque HOMR no da cajas por evento (INV-0001).
- Los ejemplos son los primeros de cada categoría en el orden de las tablas, no una muestra al azar.

## Alternativas consideradas
- **Una vista en la web de Cadenza.** Llevaría los datos de varias personas a la plataforma, con su contrato y sus permisos; el análisis se hace fuera (#400).
- **Un cuaderno de Jupyter.** Exige instalar el entorno para mirarlo.
- **Una biblioteca de gráficos desde un CDN.** Rompe el «sin red» y obliga a tener conexión para abrir los datos.
