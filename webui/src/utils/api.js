export function apiFetch(input, init = {}) {
  return fetch(input, {
    ...init,
    credentials: 'include',
  })
}
