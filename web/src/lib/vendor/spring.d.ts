export interface Spring { easing: string; ms: number; overshoot: number; duration: number; bounce: number }
export function spring(options: { duration?: number; bounce?: number; stiffness?: number; damping?: number; mass?: number; velocity?: number }): Spring
export function params(options: { duration?: number; bounce?: number; stiffness?: number; damping?: number; mass?: number }): { w0: number; zeta: number }
export function position(w0: number, zeta: number, v0?: number): (t: number) => number
