/** Number, energy, money and date formatting through Intl, in the UI language. */
import { i18n } from '@/i18n'

const cache = new Map<string, Intl.NumberFormat>()
function nf(digits: number, opts: Intl.NumberFormatOptions = {}) {
  const key = `${i18n.global.locale.value}|${digits}|${JSON.stringify(opts)}`
  let f = cache.get(key)
  if (!f) {
    f = new Intl.NumberFormat(i18n.global.locale.value, { minimumFractionDigits: digits, maximumFractionDigits: digits, ...opts })
    cache.set(key, f)
  }
  return f
}

export const NBSP = ' '
export const num = (v: number | null | undefined, digits = 0) => (v == null || !Number.isFinite(v) ? '–' : nf(digits).format(v))

/** kWh from Wh with digits by magnitude (2 below 10, 1 below 100, else 0). */
export function kwh(wh: number | null | undefined, digits?: number) {
  if (wh == null) return '–'
  const v = wh / 1000
  const d = digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2)
  return nf(d).format(v)
}

export function watts(w: number | null | undefined) {
  if (w == null) return '–'
  if (Math.abs(w) >= 1000) return `${nf(2).format(w / 1000)}${NBSP}kW`
  return `${nf(w < 10 ? 1 : 0).format(w)}${NBSP}W`
}

export function money(eur: number | null | undefined, digits = 2) {
  if (eur == null || !Number.isFinite(eur)) return '–'
  return nf(digits, { style: 'currency', currency: 'EUR' }).format(eur)
}

export const eurFromWh = (wh: number | null | undefined, price: number | null | undefined, digits = 2) =>
  wh == null || price == null ? '–' : money((wh / 1000) * price, digits)

export const pct = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? '–' : nf(0, { style: 'percent' }).format(v)

export const parseDay = (s: string) => {
  const [y, m, d] = s.slice(0, 10).split('-').map(Number)
  return new Date(y!, m! - 1, d)
}
const dtf = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(i18n.global.locale.value, o)
export const dayShort = (s: string) => dtf({ day: 'numeric', month: 'numeric' }).format(parseDay(s))
export const dayLong = (s: string) => dtf({ weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(parseDay(s))
export const dateMedium = (s: string) => dtf({ day: 'numeric', month: 'short', year: 'numeric' }).format(parseDay(s))
export const monthShort = (s: string) => dtf({ month: 'short' }).format(parseDay(s))
export const monthYear = (s: string) => dtf({ month: 'short', year: '2-digit' }).format(parseDay(s))
export const monthLong = (s: string) => dtf({ month: 'long', year: 'numeric' }).format(parseDay(s))
export const time = (t: number | Date, seconds = false) =>
  dtf({ hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' } : {}) }).format(t instanceof Date ? t : new Date(t * 1000))

export function ago(iso: string | number | null | undefined) {
  if (iso == null) return '–'
  const ms = typeof iso === 'number' ? iso * 1000 : new Date(iso).getTime()
  const sec = Math.round((ms - Date.now()) / 1000)
  const rtf = new Intl.RelativeTimeFormat(i18n.global.locale.value, { numeric: 'auto' })
  const a = Math.abs(sec)
  if (a < 45) return rtf.format(sec, 'second')
  if (a < 3600) return rtf.format(Math.round(sec / 60), 'minute')
  if (a < 86400 * 2) return rtf.format(Math.round(sec / 3600), 'hour')
  return rtf.format(Math.round(sec / 86400), 'day')
}

export function duration(s: number | null | undefined) {
  if (!s) return '–'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d) return `${d}${NBSP}d ${h}${NBSP}h`
  if (h) return `${h}${NBSP}h ${m}${NBSP}min`
  return `${m}${NBSP}min`
}
