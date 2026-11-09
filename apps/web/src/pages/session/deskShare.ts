/** Parte del ancho de la mesa de corrección que ocupa la imagen original (#341). */
export const SHARE_DEFAULT = 0.4;
export const SHARE_MIN = 0.2;
export const SHARE_MAX = 0.7;

/** Un reparto dentro de sus límites, en centésimas; lo que no es un número vuelve al inicial. */
export function clampShare(share: number): number {
  if (!Number.isFinite(share)) return SHARE_DEFAULT;
  return Math.round(Math.min(SHARE_MAX, Math.max(SHARE_MIN, share)) * 100) / 100;
}
