# Investigaciones

Investigaciones técnicas que fundamentan decisiones de arquitectura o explican por qué algo no se
hizo. Cada una dice qué se midió, cómo y cuándo; sus cifras se regeneran antes de citarse
(`CLAUDE.md` §8.4).

| ID | Tema | Resultado |
|---|---|---|
| [INV-0001](INV-0001-salidas-internas-homr-bbox-y-confianza.md) | Salidas internas de HOMR: coordenadas (`bbox`) y confianza por evento | Negativo para eventos: HOMR no da ni lo uno ni lo otro ([#14](https://github.com/sebdavid3/Cadenza/issues/14), [#31](https://github.com/sebdavid3/Cadenza/issues/31)) |
| [INV-0002](INV-0002-audiveris-frente-a-homr.md) | Audiveris 5.11.0 frente a HOMR: matices, compás con su símbolo y tresillos implícitos | En las pocas páginas medidas, Audiveris acierta en los reguladores de una página limpia y en el ¢ y los tresillos implícitos de la Sonata, pero no en las dinámicas sin OCR, y tarda 35–51 s por página: no se integra en esta entrega ([#233](https://github.com/sebdavid3/Cadenza/issues/233), [#262](https://github.com/sebdavid3/Cadenza/issues/262)) |
