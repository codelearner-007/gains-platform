import { CheckCircle, Mail, ShieldBan, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ACTIVE_BADGE_CLASS } from '@/components/admin/statusBadge';
import type { UserWithRoles } from '@/lib/services/rbac.service';

interface UserStatusBadgeProps {
  user: UserWithRoles;
}

export function UserStatusBadge({ user }: UserStatusBadgeProps) {
  return (
    <div className="flex flex-col gap-1">
      {user.is_banned ? (
        <Badge
          variant="secondary"
          className="w-fit bg-destructive/10 text-destructive border-destructive/20"
        >
          <ShieldBan className="h-3 w-3 mr-1" />
          Banned
        </Badge>
      ) : (
        <Badge variant="secondary" className={ACTIVE_BADGE_CLASS}>
          <CheckCircle className="h-3 w-3 mr-1" />
          Active
        </Badge>
      )}
      {user.email_confirmed_at ? (
        <Badge variant="outline" className="w-fit text-xs">
          <Mail className="h-3 w-3 mr-1" />
          Verified
        </Badge>
      ) : (
        <Badge variant="outline" className="w-fit text-xs text-muted-foreground">
          <XCircle className="h-3 w-3 mr-1" />
          Unverified
        </Badge>
      )}
    </div>
  );
}
