import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FileQuestion } from 'lucide-react';

export default function AppNotFound() {
  return (
    <div className="flex items-center justify-center min-h-screen p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex justify-center mb-4">
            <FileQuestion className="h-16 w-16 text-muted-foreground" />
          </div>
          <CardTitle className="text-center">Page Not Found</CardTitle>
          <CardDescription className="text-center">
            This page doesn&apos;t exist in the application
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/app" className="w-full">
            <Button className="w-full">
              Return to dashboard
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
