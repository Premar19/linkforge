import type { AuthResponse } from './types'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const message = typeof body.detail === 'string' ? body.detail : res.statusText
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export async function signup(
  tenantName: string,
  tenantSlug: string,
  email: string,
  password: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_name: tenantName,
      tenant_slug: tenantSlug,
      email,
      password,
    }),
  })
  return handleResponse<AuthResponse>(res)
}

export async function login(
  tenantSlug: string,
  email: string,
  password: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
  })
  return handleResponse<AuthResponse>(res)
}

export async function createLink(token: string, targetUrl: string): Promise<void> {
  const res = await fetch(`${API_BASE}/links`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ target_url: targetUrl }),
  })
  await handleResponse(res)
}

export function streamUrl(token: string): string {
  return `${API_BASE}/dashboard/stream?token=${encodeURIComponent(token)}`
}

export function redirectUrl(code: string): string {
  return `${API_BASE}/r/${code}`
}
