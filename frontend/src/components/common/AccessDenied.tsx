import Link from 'next/link';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface AccessDeniedProps {
  message?: string;
  returnTo?: string;
  returnLabel?: string;
}

export default function AccessDenied({
  message = 'You do not have permission to access this page.',
  returnTo = '/app',
  returnLabel = 'Back to app',
}: AccessDeniedProps) {
  return (
    <div className="flex items-center justify-center min-h-[70vh] px-6">
      <div className="text-center space-y-6 max-w-md">
        <div className="flex justify-center">
          <div className="relative">
            <div className="absolute inset-0 rounded-full bg-destructive/10 blur-2xl" />
            <div className="relative h-14 w-14 rounded-2xl border border-destructive/20 bg-destructive/5 flex items-center justify-center">
              <ShieldAlert className="h-6 w-6 text-destructive" />
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Access denied
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">{message}</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-2 justify-center pt-2">
          <Button asChild>
            <Link href={returnTo}>{returnLabel}</Link>
          </Button>
        </div>

        <p className="text-xs text-muted-foreground/80">
          If you believe you should have access, please contact your administrator.
        </p>
      </div>
    </div>
  );
}
