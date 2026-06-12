import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { getMe } from '@/lib/server/me';
import { Button } from '@/components/ui/button';

export default async function AuthAwareButtons({ variant = 'primary' }: { variant?: string }) {
  const user = await getMe();
  const isAuthenticated = !!user;

  if (variant === 'nav') {
    return isAuthenticated ? (
      <Button asChild size="sm">
        <Link href="/app">Go to dashboard</Link>
      </Button>
    ) : (
      <Button asChild size="sm">
        <Link href="/auth/login">Sign in</Link>
      </Button>
    );
  }

  return isAuthenticated ? (
    <Button asChild size="xl" className="btn-glow">
      <Link href="/app">
        Go to dashboard
        <ArrowRight className="ml-1 h-4 w-4" />
      </Link>
    </Button>
  ) : (
    <>
      <Button asChild size="xl" className="btn-glow">
        <Link href="/auth/login">
          Sign in
          <ArrowRight className="ml-1 h-4 w-4" />
        </Link>
      </Button>
      <Button asChild size="xl" variant="outline">
        <Link href="#features">See what&apos;s included</Link>
      </Button>
    </>
  );
}
