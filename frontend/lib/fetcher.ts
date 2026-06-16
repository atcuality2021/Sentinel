export const fetcher = (url: string) =>
  fetch(url, { credentials: "include" }).then((r) => {
    if (r.status === 401) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
      return undefined
    }
    if (!r.ok) throw new Error(`${r.status}`)
    return r.json()
  })
