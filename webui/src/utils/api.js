export function apiFetch(input, init = {}) {
  return fetch(input, {
    ...init,
    credentials: 'include',
  }).then((response) => {
    if (response.status === 401) {
      const url = typeof input === 'string' ? input : input.url
      const isAuthEndpoint =
        url.endsWith('/auth/login') ||
        url.endsWith('/auth/register') ||
        url.endsWith('/auth/me')
      if (!isAuthEndpoint && typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return response
  })
}
