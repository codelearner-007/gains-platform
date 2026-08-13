import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { getMe } from '@/lib/server/me';
import { Button } from '@/components/ui/button';

export default async function AuthAwareButtons({ variant = 'primary' }: { variant?: string }) {
  const user = await getMe();
  const href = user ? '/app' : '/auth/login';
  const label = user ? 'Go to dashboard' : 'Sign in';

  if (variant === 'nav') {
    return (
      <Button asChild size="sm" variant="destructive" className="rounded-full">
        <Link href={href}>{label}</Link>
      </Button>
    );
  }

  return (
    <Button asChild size="xl" variant="destructive">
      <Link href={href}>
        {label}
        <ArrowRight className="ml-1 h-4 w-4" />
      </Link>
    </Button>
  );
}
