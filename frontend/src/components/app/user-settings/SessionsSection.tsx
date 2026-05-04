'use client';

import { useState, useEffect } from 'react';
import { formatDistanceToNow, format } from 'date-fns';
import { UAParser } from 'ua-parser-js';
import { Monitor, Smartphone, Tablet, Globe, Loader2, AlertTriangle, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { sessionService, type SessionInfo } from '@/lib/services/session.service';

function getDeviceIcon(deviceType: string | undefined) {
  switch (deviceType) {
    case 'mobile':
      return Smartphone;
    case 'tablet':
      return Tablet;
    default:
      return Monitor;
  }
}

function parseUserAgent(ua: string | null) {
  if (!ua) return { browser: 'Unknown', os: 'Unknown', device: undefined as string | undefined };
  const parser = new UAParser(ua);
  const browser = parser.getBrowser();
  const os = parser.getOS();
  const device = parser.getDevice();
  return {
    browser: browser.name ? `${browser.name} ${browser.version || ''}`.trim() : 'Unknown browser',
    os: os.name ? `${os.name} ${os.version || ''}`.trim() : 'Unknown OS',
    device: device.type,
  };
}

export function SessionsSection() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    async function loadSessions() {
      try {
        const data = await sessionService.getSessions();
        // Sort: current session first, then by most recent
        const sorted = [...data.sessions].sort((a, b) => {
          if (a.is_current) return -1;
          if (b.is_current) return 1;
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        });
        setSessions(sorted);
      } catch {
        toast.error('Failed to load sessions');
      } finally {
        setLoading(false);
      }
    }
    loadSessions();
  }, []);

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    setRevoking(true);
    try {
      await sessionService.revokeSession(revokeTarget);
      setSessions((prev) => prev.filter((s) => s.id !== revokeTarget));
      toast.success('Session revoked');
    } catch {
      toast.error('Failed to revoke session');
    } finally {
      setRevoking(false);
      setRevokeTarget(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <Card className="border-border/50 shadow-sm">
        <CardContent className="flex flex-col items-center justify-center py-12 text-center">
          <Globe className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">No active sessions found</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Alert className="border-amber-500/30 bg-amber-500/5">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertDescription className="text-amber-700 dark:text-amber-400">
          Revoked sessions may take up to 60 minutes to fully terminate due to token expiry.
        </AlertDescription>
      </Alert>

      <div className="space-y-3">
        {sessions.map((session) => {
          const { browser, os, device } = parseUserAgent(session.user_agent);
          const DeviceIcon = getDeviceIcon(device);
          const lastActive = session.refreshed_at || session.updated_at || session.created_at;

          return (
            <Card key={session.id} className="border-border/50 shadow-sm">
              <CardContent className="flex items-start gap-4 p-4">
                <div className="flex-shrink-0 mt-1">
                  <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                    <DeviceIcon className="h-5 w-5 text-muted-foreground" />
                  </div>
                </div>

                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{browser}</span>
                    {session.is_current && (
                      <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20 text-xs">
                        Current session
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{os}</p>
                  {session.ip && (
                    <p className="text-xs text-muted-foreground font-mono">{session.ip}</p>
                  )}
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>
                      Active {formatDistanceToNow(new Date(lastActive), { addSuffix: true })}
                    </span>
                    <span>
                      Created {format(new Date(session.created_at), 'MMM d, yyyy')}
                    </span>
                  </div>
                </div>

                {!session.is_current && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setRevokeTarget(session.id)}
                    className="text-destructive hover:text-destructive hover:bg-destructive/10 flex-shrink-0"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <AlertDialog open={!!revokeTarget} onOpenChange={(open) => !open && setRevokeTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke session</AlertDialogTitle>
            <AlertDialogDescription>
              This will sign out the selected session. The device will need to sign in again to access your account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoking}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRevoke}
              disabled={revoking}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {revoking ? 'Revoking...' : 'Revoke'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
