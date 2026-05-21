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
