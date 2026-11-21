import { createI18n } from 'vue-i18n'
import de from './de'
import en from './en'

export type Locale = 'de' | 'en'
const stored = (() => { try { return localStorage.getItem('tiris.locale') } catch { return null } })()
const initial: Locale = stored === 'de' || stored === 'en' ? stored : navigator.language.startsWith('de') ? 'de' : 'en'

export const i18n = createI18n({ legacy: false, locale: initial, fallbackLocale: 'en', messages: { de, en } })

export function setLocale(l: Locale) {
  i18n.global.locale.value = l
  document.documentElement.lang = l
  try { localStorage.setItem('tiris.locale', l) } catch { /* private mode */ }
}
document.documentElement.lang = initial
