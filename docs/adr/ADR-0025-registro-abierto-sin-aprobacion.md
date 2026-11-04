# ADR-0025: Registro abierto: la cuenta queda activa al crearse

- **Estado:** Aceptado
- **Fecha:** 2026-10-23
- **Decisores:** Dirección del proyecto Cadenza (decisión del responsable el 2026-10-23), Equipo de Desarrollo
- **Relacionado:** [ADR-0022](ADR-0022-registro-de-cuentas-con-activacion.md) (enmienda sus §4 y §9), [ADR-0012](ADR-0012-autenticacion-e-identidad.md), [ADR-0023](ADR-0023-despliegue-publico-con-tailscale-funnel.md), [ADR-0024](ADR-0024-transcripciones-simultaneas.md)

---

## Contexto

ADR-0022 abrió el registro con **activación por un investigador**:
- la cuenta nacía inactiva;
- no podía entrar hasta que un investigador la activaba en `/cuentas`;
- el registro se cerraba con 503 al llegar a 50 cuentas pendientes.

Antes del despliegue público (#157), el responsable decide que el registro sea abierto: cualquiera crea una cuenta y prueba Cadenza en el momento, sin esperar a nadie.

## Decisión

1. **Cuenta activa al crearse.** `POST /auth/register` crea un transcriptor activo. Enmienda el §4 de ADR-0022.
2. **Sin tope de pendientes.** Ya no hay cuentas pendientes. Desaparecen `CADENZA_REGISTRATION_MAX_PENDING`, la excepción `RegistrationClosed` y el 503 del registro. Enmienda el §9 de ADR-0022.
3. **Se mantiene el resto de ADR-0022:**
   - rol fijo `transcriptor`;
   - solo usuario y contraseña;
   - la marca `self_registered`, que excluye estas cuentas de los datos del estudio (`exp_10`, `ml export-effort`);
   - el límite de registros por IP (red /64 en IPv6);
   - el interruptor `CADENZA_REGISTRATION_ENABLED`.
4. **Moderación.** Un investigador puede desactivar una cuenta con `PATCH /users/{id}`. Una cuenta desactivada no entra, como con unas credenciales incorrectas, y su token vigente deja de valer en la siguiente petición: la API comprueba `active` en cada una. `/cuentas` queda como lista para activar o desactivar, sin estado de espera.
5. **Interfaz.**
   - `/registro` crea la cuenta, entra con ella y lleva a `/transcripcion`. Si ese acceso falla, dice que la cuenta existe y enlaza a entrar.
   - `/registro`, `/entrar` y la landing dejan de hablar de activación.

## Consecuencias

### Positivas
- Quien llega a la página pública prueba Cadenza sin esperar.
- Menos piezas: sin tope de pendientes ni estado de espera; desaparece la deuda D56.

### Negativas / Riesgos
- Cualquiera puede consumir CPU y disco del servidor. Los frenos son:
  - el límite de registros por IP (5 por hora por defecto) y los límites de Nginx (ADR-0023);
  - el tope de transcripciones simultáneas (ADR-0024);
  - el tamaño máximo de imagen (20 MB);
  - la moderación por desactivación.

  No hay cuotas por cuenta ni borrado de sesiones o cuentas: las imágenes y las sesiones de quien prueba se quedan en el disco y en la base de datos.
- Las cuentas del registro comparten los huecos de transcripción (ADR-0024) con los participantes del estudio: muchas pruebas a la vez pueden dar 503 también al estudio.
- El límite de registros por IP vive en la memoria del proceso: se pierde al reiniciar la API y depende de la IP real que da el proxy (ADR-0023).
- Cualquiera puede elegir un nombre como `admin` o `investigador`: no hay nombres reservados, y el rol sigue siendo transcriptor. El 409 dice si un nombre existe, como ya pasaba con ADR-0022.
- `/cuentas` carga todas las cuentas de una vez, sin paginar.
- Las cuentas del registro no se distinguían de las del estudio en el plano offline (`DatasetBuilder`, D55); con registro abierto puede haber más. Resuelta en [#191](https://github.com/sebdavid3/Cadenza/issues/191): el `DatasetBuilder` las deja fuera salvo que se pida incluirlas.

Los límites del registro abierto quedan como deuda (D59), para resolverlos si el uso lo pide.

## Alternativas consideradas

1. **Mantener la activación (ADR-0022).** Descartada por decisión del responsable: frena a quien quiere probar.
2. **Activación automática con CAPTCHA.** Descartada: un CAPTCHA es un servicio de terceros y no se añade sin permiso.
