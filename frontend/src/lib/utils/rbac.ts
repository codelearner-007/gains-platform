export function hasPermission(
  userPermissions: string[],
  required: string
): boolean {
  return userPermissions.includes(required);
}

export function hasAnyPermission(
  userPermissions: string[],
  required: string[]
): boolean {
  return required.some(perm => userPermissions.includes(perm));
}

export function hasAllPermissions(
  userPermissions: string[],
  required: string[]
): boolean {
  return required.every(perm => userPermissions.includes(perm));
}

export function checkHierarchy(
  userLevel: number,
  requiredLevel: number
): boolean {
  return userLevel >= requiredLevel;
}
