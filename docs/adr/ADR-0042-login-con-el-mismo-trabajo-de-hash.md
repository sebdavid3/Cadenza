# ADR-0042: El inicio de sesión hace el mismo trabajo de hash en los tres casos del 401

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Decisores:** Equipo de Desarrollo (decisión técnica compatible con ADR-0012, CLAUDE.md §9)
- **Relacionado:** [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md), [ADR-0025](ADR-0025-registro-abierto-sin-aprobacion.md), [#143](https://github.com/sebdavid3/Cadenza/issues/143), [#194](https://github.com/sebdavid3/Cadenza/issues/194), [#226](https://github.com/sebdavid3/Cadenza/issues/226)

---

## Contexto

`POST /auth/login` responde a un usuario inexistente, una contraseña incorrecta y una cuenta desactivada con el mismo 401, el mismo cuerpo y la misma cabecera (#143). El tiempo de respuesta, en cambio, los distinguía. `authenticate` devolvía el 401 sin calcular nada si el usuario no existía o no estaba activo, y solo verificaba la contraseña con Argon2id (los valores por defecto de argon2-cffi 25.1.0) cuando la cuenta estaba activa. Una sola petición por nombre bastaba para separar una **cuenta activa** de un **usuario inexistente o desactivado**: en las medidas de #226, de mediana, unos 4 ms frente a 42 ms en memoria y 5 ms frente a 58 ms por HTTP, sin solaparse.

El límite del login va por IP y nombre, así que no frena un sondeo de muchos nombres; en el despliegue lo frena Nginx, con 10 peticiones por minuto por visitante.

## Decisión

1. **Siempre se verifica una vez.** `authenticate` llama a `PasswordHasher.verify` exactamente una vez, haya cuenta o no y esté activa o no, y decide después:
   - **Con cuenta** (activa o desactivada), contra su propio hash. Una cuenta desactivada con la contraseña correcta sigue dando 401.
   - **Sin cuenta**, contra un hash de relleno del adaptador.
2. **El hash de relleno es parte del puerto.** `PasswordHasher` gana el método abstracto `dummy_hash() -> str`: un hash con los mismos parámetros que `hash()` que ninguna contraseña verifica. `packages/application` no conoce Argon2 (CLAUDE.md §10.2). Los adaptadores:
   - **`Argon2PasswordHasher`** lo calcula con su propio `argon2.PasswordHasher`, sobre una contraseña aleatoria de `secrets.token_urlsafe(32)` que no se guarda. Si cambian los parámetros, el relleno cambia con ellos. Lo calcula una sola vez, la primera vez que hace falta, con un cerrojo para que dos peticiones simultáneas no lo calculen dos veces. Calcularlo al construir el adaptador encarecería cada `create_app` de las pruebas en unos 45 ms.
   - **`InMemoryPasswordHasher`**, el doble de las pruebas, devuelve un valor fijo que ninguna contraseña verifica.
3. **Se prueba contando, no midiendo.** Una prueba del caso de uso, con un `PasswordHasher` que cuenta las llamadas, comprueba la verificación única en los tres casos del 401 y en el acceso correcto. Otra prueba del adaptador comprueba que el relleno usa los parámetros de un hash real (`$argon2id$v=19$m=…,t=…,p=…`). Una prueba de tiempos en la CI sería frágil.

## Medida

El 2026-10-31, con la misma comprobación de #226: los cuatro casos intercalados en cada ronda, una petición de calentamiento por caso fuera de la medida, 50 peticiones por caso, el límite de intentos desactivado (`login_rate_limit_max_attempts=0`), cuentas locales y contraseñas de `secrets.token_urlsafe`. **En memoria**, `TestClient` sobre `create_app` con SQLite en memoria; **por HTTP**, uvicorn en `127.0.0.1` (en un hilo del mismo proceso que el cliente, que abre una conexión por petición) con SQLite en disco. Sin HOMR. Windows 11, Python 3.12.14, argon2-cffi 25.1.0, FastAPI 0.141.1, uvicorn 0.53.0. «Antes» es el código de `dev` en ac615fe; «después», esta rama. Tiempos en ms.

| Caso | Antes, en memoria: mediana (p10–p90) | Después, en memoria | Antes, por HTTP | Después, por HTTP |
| :--- | ---: | ---: | ---: | ---: |
| Usuario inexistente (401) | 4,8 (4,3–5,8) | 49,4 (46,5–51,6) | 3,9 (3,2–4,4) | 49,0 (47,8–51,2) |
| Contraseña incorrecta (401) | 46,3 (45,4–50,9) | 49,5 (46,6–50,9) | 45,6 (44,4–48,7) | 48,9 (47,6–53,2) |
| Cuenta desactivada (401) | 4,8 (4,3–5,4) | 49,6 (46,9–50,8) | 4,0 (3,2–4,4) | 48,7 (47,4–51,4) |
| Referencia: contraseña correcta (200) | 47,0 (45,6–50,2) | 49,4 (47,5–52,0) | 46,4 (45,2–48,6) | 49,3 (48,0–53,1) |

Antes, el máximo de los casos rápidos (16,2 ms en memoria y 5,2 ms por HTTP) quedaba por debajo del mínimo de la contraseña incorrecta (44,8 y 43,6 ms). Después, las medianas de los tres casos del 401 difieren menos de 0,5 ms y sus intervalos p10–p90 se solapan.

## Consecuencias

### Positivas
- El tiempo ya no separa una cuenta activa de un usuario inexistente o desactivado. El 409 del registro abierto sigue diciendo si un nombre existe (ADR-0025), pero con su propio límite por IP (ADR-0022 §6) y sin distinguir cuentas activas de desactivadas.
- El contrato v1, las respuestas y el límite de intentos no cambian.

### Negativas / Riesgos
- Cada 401 de un usuario inexistente o desactivado cuesta ahora una verificación de Argon2id (unos 45 ms de CPU), como ya costaban la contraseña incorrecta y el acceso correcto. En el despliegue lo acota el límite de Nginx (10 por minuto y visitante); el de la API, por IP y nombre, no frena un sondeo de muchos nombres.
- El primer usuario inexistente de cada proceso paga además el cálculo del relleno, una sola vez.
- `verify` usa los parámetros guardados en cada hash, y el relleno, los actuales. Si cambiaran los parámetros (por ejemplo, otros valores por defecto de argon2-cffi), las cuentas creadas antes tardarían distinto que un usuario inexistente hasta volver a calcular su hash. Hoy todos los hashes salen de `Argon2PasswordHasher.hash` con los mismos valores; volver a calcularlos al iniciar sesión (`check_needs_rehash`) queda para cuando cambien.
- Un `PasswordHasher` nuevo tiene que implementar `dummy_hash()` con sus parámetros reales; si no, el tiempo volvería a delatar a los usuarios inexistentes.
- **No medido:** el despliegue público a través de Tailscale Funnel y Nginx, con la latencia y el ruido de la red.
