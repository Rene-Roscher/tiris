/** Turns collector run messages (one finding per line) into short, readable lines; the raw text stays available. */
export type RunLineKind = 'session' | 'discovery' | 'misdated' | 'timeout' | 'unreachable' | 'other'
export interface RunLine { kind: RunLineKind; device?: string; ip?: string; raw: string; warn: boolean }

const DEVICE = /^(?:WARN:\s*)?(.+?)\s+\(P\d+\w*, [0-9A-F]{6}\):/

export function parseRun(message: string | null): RunLine[] {
  if (!message) return []
  return message.split('\n').filter(Boolean).map((raw) => {
    const warn = raw.startsWith('WARN:')
    const device = DEVICE.exec(raw)?.[1]?.trim()
    const ip = /ip: "([\d.]+)"/.exec(raw)?.[1]
    let kind: RunLineKind = 'other'
    if (/SESSION_TIMEOUT/.test(raw)) kind = 'session'
    else if (/Discovery/.test(raw)) kind = 'discovery'   // a plug busy with tiris' own session often refuses a second handshake
    else if (/misdated/.test(raw)) kind = 'misdated'
    else if (/[Tt]imeout|timed out/.test(raw)) kind = 'timeout'
    else if (/unreachable|No route|Connection refused/i.test(raw)) kind = 'unreachable'
    return { kind, device, ip, raw, warn }
  })
}

/** Same finding for several devices becomes one line with all names. */
export function groupRun(lines: RunLine[], nameByIp: Record<string, string> = {}) {
  const out = new Map<string, { kind: RunLineKind; names: string[]; raw: string[]; warn: boolean }>()
  for (const l of lines) {
    const key = l.kind === 'other' ? `other:${l.raw}` : l.kind
    const g = out.get(key) ?? { kind: l.kind, names: [], raw: [], warn: l.warn }
    const name = l.device ?? (l.ip ? nameByIp[l.ip] ?? l.ip : undefined)
    if (name && !g.names.includes(name)) g.names.push(name)
    g.raw.push(l.raw)
    out.set(key, g)
  }
  return [...out.values()]
}
