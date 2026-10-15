// Requests go to this app's own /api/* routes (app/api/[...path]/route.ts), which
// forward to the backend and attach the API key on the server.
export const API_URL = '';

export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, init);
}
