// Talking to the same server as the website. Every call carries the player's sign-in
// (X-Session) and, where they have one, the closed-test passcode (X-Passcode).
import { API_BASE } from './config';

export type Creds = { session?: string | null; passcode?: string | null };

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly signIn = false) {
    super(message);
  }
}

export function formBody(fields: Record<string, string | number | undefined>): string {
  return Object.entries(fields)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
}

export function headers({ session, passcode }: Creds): Record<string, string> {
  return {
    ...(session ? { 'X-Session': session } : {}),
    ...(passcode ? { 'X-Passcode': passcode } : {}),
  };
}

async function read<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (res.ok) return data as T;
  const error = (data as { error?: string; signin?: boolean });
  throw new ApiError(error.error || `Something went wrong (${res.status}).`, res.status, !!error.signin);
}

async function call<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("Couldn't reach the server. Check your connection and try again.", 0);
  }
  return read<T>(res);
}

export function apiGet<T>(path: string, creds: Creds): Promise<T> {
  return call<T>(path, { headers: headers(creds) });
}

export function apiPost<T>(path: string, fields: Record<string, string | number | undefined>, creds: Creds): Promise<T> {
  return call<T>(path, {
    method: 'POST',
    headers: { ...headers(creds), 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formBody(fields),
  });
}

// A picture for /api/aim or a match's marking picture.
export function apiPostPicture<T>(path: string, fileUri: string, extra: Record<string, string>, creds: Creds): Promise<T> {
  const body = new FormData();
  body.append('file', { uri: fileUri, name: 'court.jpg', type: 'image/jpeg' } as unknown as Blob);
  Object.entries(extra).forEach(([k, v]) => body.append(k, v));
  return call<T>(path, { method: 'POST', headers: headers(creds), body });
}
