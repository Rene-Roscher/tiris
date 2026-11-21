/** Promise-based confirm: `if (await confirm({ title, body, action, danger })) ...`. Rendered once by ConfirmHost. */
import { shallowRef } from 'vue'

export interface ConfirmRequest { title: string; body?: string; detail?: string; action: string; danger?: boolean }
export const pending = shallowRef<(ConfirmRequest & { resolve: (ok: boolean) => void }) | null>(null)

export function confirm(req: ConfirmRequest): Promise<boolean> {
  pending.value?.resolve(false)
  return new Promise((resolve) => { pending.value = { ...req, resolve } })
}
