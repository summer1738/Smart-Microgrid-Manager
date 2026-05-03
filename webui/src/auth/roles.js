export const ROLE_RANK = {
  viewer: 0,
  operator: 1,
  admin: 2,
}

export function roleMeetsMin(role, minRole) {
  const current = ROLE_RANK[role]
  const required = ROLE_RANK[minRole]
  if (required === undefined) return true
  if (current === undefined) return false
  return current >= required
}
