# ADR-0042: El inicio de sesión hace el mismo trabajo de hash en los tres casos del 401

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0012, CLAUDE.md §9)
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md), [#143](https://github.com/sebdavid3/Cadenza/issues/143), [#194](https://github.com/sebdavid3/Cadenza/issues/194), [#226](https://github.com/sebdavid3/Cadenza/issues/226)

---

## Contexto

`POST /auth/login` responde a un usuario inexistente, una contraseña incorrecta y una cuenta desactivada con el mismo 401, el mismo cuerpo y la misma cabecera (#143). El tiempo de respuesta, en cambio, los distinguía. `authenticate` devolvía el 401 sin calcular nada si el usuario no existía o no estaba activo, y solo verificaba la contraseña con Argon2id (unos 45 ms con los valores por defecto de argon2-cffi 25.1.0) cuando la cuenta estaba activa. Una sola petición por nombre bastaba para separar una **cuenta activa** de un **usuario inexistente o desactivado**: en local, los casos rápidos tardaban unos 4 ms y los lentos, unos 46 ms, sin solaparse (cifras en #226).

El límite del login va por IP y nombre, así que no frena un sondeo de muchos nombres; en el despliegue lo frena Nginx, con 10 peticiones por minuto por visitante.

## Decisión

1. **Siempre se verifica una vez.** `authenticate` llama a `PasswordHasher.verify` exactamente una vez, haya cuenta o no y esté activa o no, y decide después:
   - **Con cuenta** (activa o desactivada), contra su propio hash. Una cuenta desactivada con la contraseña correcta sigue dando 401.
   - **Sin cuenta**, contra un hash de relleno del adaptador.
2. **El hash de relleno es parte del puerto.** `PasswordHasher` gana el método abstracto `dummy_hash() -> str`: un hash con los mismos parámetros que `hash()` que ninguna contraseña verifica. `packages/application` no conoce Argon2 (CLAUDE.md §10.2). Los adaptadores:
   - **`Argon2PasswordHasher`** lo calcula con su propio `argon2.PasswordHasher`, sobre una contraseña aleatoria de `secrets.token_urlsafe(32)` que no se guarda. Si cambian los parámetros, el relleno cambia con ellos. Lo calcula una sola vez, la primera vez que hace falta, con un cerrojo para que dos peticiones simultáneas no lo calculen dos veces. Calcularlo al construir el adaptador encarecería cada `create_app` de las pruebas en unos 45 ms.
   - **`InMemoryPasswordHasher`**, el doble de las pruebas, devuelve un valor fijo que ninguna contraseña verifica.
3. **Se prueba contando, no midiendo.** Una prueba del caso de uso, con un `PasswordHasher` que cuenta las llamadas, comprueba la verificación única en los tres casos del 401 y en el acceso correcto. Otra prueba del adaptador comprueba que el relleno usa los parámetros de un hash real (`$argon2id$v=19$m=…,t=…,p=…`). Una prueba de tiempos en la CI sería frágil.

La comprobación de tiempos se repitió el 2026-10-31 en memoria y por HTTP, con los tres casos del 401 dentro del ruido. Las cifras están en el issue y en el PR.

## Consecuencias

### Positivas
- El tiempo ya no separa una cuenta activa de un usuario inexistente o desactivado. El 409 del registro abierto sigue diciendo si un nombre existe (ADR-0025), pero con su propio límite por IP (ADR-0022 §6) y sin distinguir cuentas activas de desactivadas.
- El contrato v1, las respuestas y el límite de intentos no cambian.

### Negativas / Riesgos
- Cada 401 de un usuario inexistente o desactivado cuesta ahora una verificación de Argon2id (unos 45 ms de CPU), como ya costaban la contraseña incorrecta y el acceso correcto. Los límites del login (5 fallos por IP y nombre en la API; 10 por minuto y visitante en Nginx) acotan ese gasto.
- El primer usuario inexistente de cada proceso paga además el cálculo del relleno, una sola vez.
- Un `PasswordHasher` nuevo tiene que implementar `dummy_hash()` con sus parámetros reales; si no, el tiempo volvería a delatar a los usuarios inexistentes.
- **No medido:** el despliegue público a través de Tailscale Funnel y Nginx, con la latencia y el ruido de la red.
