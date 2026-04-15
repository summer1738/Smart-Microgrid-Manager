/** Role hierarchy for route and nav visibility (viewer < operator < admin). */
export const ROLE_RANK = {
  viewer: 0,
  operator: 1,
  admin: 2,
}

export function roleMeetsMin(role, minRole) {
  const r = ROLE_RANK[role]
  const m = ROLE_RANK[minRole]
  if (m === undefined) return true
  if (r === undefined) return false
  return r >= m
}
