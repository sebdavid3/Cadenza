/**
 * El reloj del esfuerzo (#188, ADR-0050, protocolo §3.4): suma el tiempo con la página de la
 * sesión visible y con actividad. Cada pausa sin actividad (ni teclado, ni ratón, ni toque) suma
 * como mucho el umbral; lo que la pestaña está oculta, o la medición parada, no suma nada.
 *
 * Es puro: cada método recibe el instante `t` en milisegundos de un reloj monótono
 * (`performance.now()` en la vista), así que se prueba sin esperar.
 */
export class EffortClock {
  private total: number;
  /** Hasta dónde está contado el tiempo del tramo en curso. */
  private from = 0;
  /** Última actividad, o el comienzo del tramo, que cuenta como tal. */
  private lastActivity = 0;
  private counting = false;

  constructor(
    private readonly idleMs: number,
    initialMs = 0,
  ) {
    this.total = initialMs;
  }

  /** Si está sumando tiempo ahora mismo. */
  get running(): boolean {
    return this.counting;
  }

  /**
   * Empieza a contar en `t`: al cargar la vista, al volver a la pestaña o al reanudar. Quien
   * vuelve a la página empieza una pausa en ese momento, como si acabara de moverse.
   */
  start(t: number): void {
    if (this.counting) return;
    this.counting = true;
    this.from = t;
    this.lastActivity = t;
  }

  /** Deja de contar en `t` (la pestaña se oculta, se finaliza): lo contado hasta ahí queda. */
  stop(t: number): void {
    this.settle(t);
    this.counting = false;
  }

  /** Una tecla, un movimiento o un clic del ratón, un toque: la pausa en curso acaba en `t`. */
  activity(t: number): void {
    this.settle(t);
    if (this.counting) this.lastActivity = Math.max(this.lastActivity, t);
  }

  /** El tiempo contado hasta `t`. */
  read(t: number): number {
    this.settle(t);
    return this.total;
  }

  private settle(t: number): void {
    if (!this.counting || t <= this.from) return;
    // De la pausa desde la última actividad solo cuenta el umbral.
    const end = Math.min(t, this.lastActivity + this.idleMs);
    if (end > this.from) this.total += end - this.from;
    this.from = t;
  }
}
