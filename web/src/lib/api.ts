/** Small JSON client for the tiris API. Errors carry the server's `detail` message. */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = (data as { detail?: unknown }).detail
    const msg = Array.isArray(d) ? d.map((x: { msg?: string }) => x.msg).join(', ') : String(d ?? res.statusText)
    if (res.status === 401 && window.location.pathname !== '/login') window.dispatchEvent(new Event('tiris:login'))
    throw new ApiError(res.status, msg)
  }
  return data as T
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: unknown) => request<T>('PUT', url, body),
  patch: <T>(url: string, body: unknown) => request<T>('PATCH', url, body),
  del: <T>(url: string) => request<T>('DELETE', url),
}
