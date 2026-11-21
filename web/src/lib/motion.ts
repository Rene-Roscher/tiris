/**
 * Motion tokens (interface-motion). Each curve is a CSS custom property with a cubic-bezier() fallback and a
 * duration next to it (app.css). Here they are replaced once at startup by springs generated as linear(), where
 * the browser supports linear(). Components only read the tokens.
 *
 *   settle  0.30 s, bounce 0  popovers, menus, the mobile sheet (settles after 400 ms)
 *   calm    0.35 s, bounce 0  dialogs (settles after 471 ms)
 */
import { spring } from './vendor/spring.js'

const CURVES = { settle: { duration: 0.3, bounce: 0 }, calm: { duration: 0.35, bounce: 0 } } as const

export function installSprings() {
  if (typeof CSS === 'undefined' || !CSS.supports('transition-timing-function', 'linear(0, 1)')) return
  const root = document.documentElement.style
  for (const [name, opts] of Object.entries(CURVES)) {
    const s = spring(opts)
    root.setProperty(`--ease-${name}`, s.easing)
    root.setProperty(`--ease-${name}-ms`, `${s.ms}ms`)
  }
}
