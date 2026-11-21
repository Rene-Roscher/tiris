// Fails when de and en differ in keys or a message contains vue-i18n syntax characters by accident.
import { pathToFileURL } from 'node:url'
const load = async (f) => (await import(pathToFileURL(f).href)).default
const flat = (o, p = '') => Object.entries(o).flatMap(([k, v]) => (typeof v === 'object' ? flat(v, `${p}${k}.`) : [[`${p}${k}`, v]]))
const [de, en] = await Promise.all([load('src/i18n/de.ts'), load('src/i18n/en.ts')])
const D = new Map(flat(de)), E = new Map(flat(en))
const missing = [...D.keys()].filter((k) => !E.has(k)).map((k) => `en missing ${k}`)
  .concat([...E.keys()].filter((k) => !D.has(k)).map((k) => `de missing ${k}`))
const bad = [...D, ...E].filter(([, v]) => /[@$|]/.test(v)).map(([k]) => `syntax char in ${k}`)
const problems = [...missing, ...bad]
console.log(problems.length ? problems.join('\n') : `ok: ${D.size} keys in both locales`)
process.exit(problems.length ? 1 : 0)
