'use client';

import { useState, useEffect } from 'react';
import { useTheme } from 'next-themes';
import { Sun, Moon, Monitor, Check, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { profileService } from '@/lib/services/profile.service';
import { cn } from '@/lib/utils';

const COMMON_TIMEZONES = [
  { value: 'UTC', label: 'UTC' },
  { value: 'America/New_York', label: 'Eastern Time (US)' },
  { value: 'America/Chicago', label: 'Central Time (US)' },
  { value: 'America/Denver', label: 'Mountain Time (US)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (US)' },
  { value: 'Europe/London', label: 'London (GMT)' },
  { value: 'Europe/Paris', label: 'Paris (CET)' },
  { value: 'Europe/Berlin', label: 'Berlin (CET)' },
  { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
  { value: 'Asia/Shanghai', label: 'Shanghai (CST)' },
  { value: 'Australia/Sydney', label: 'Sydney (AEST)' },
  { value: 'Pacific/Auckland', label: 'Auckland (NZST)' },
];

export function PreferencesSection() {
  const { theme, setTheme } = useTheme();
  const [timezone, setTimezone] = useState<string>('UTC');
  const [loading, setLoading] = useState(true);
  const [savingTimezone, setSavingTimezone] = useState(false);

  useEffect(() => {
    async function loadPreferences() {
      try {
        const profile = await profileService.getProfile();
        if (profile.timezone) setTimezone(profile.timezone);
      } catch {
        // Profile fetch failed - use defaults
      } finally {
        setLoading(false);
      }
    }
    loadPreferences();
  }, []);

  const handleTimezoneChange = async (tz: string) => {
    const previousTz = timezone;
    setTimezone(tz);
    setSavingTimezone(true);
    try {
      await profileService.updatePreferences({ timezone: tz });
      toast.success('Timezone updated');
    } catch {
      setTimezone(previousTz);
      toast.error('Failed to save timezone');
    } finally {
      setSavingTimezone(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Theme */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Theme</CardTitle>
          <CardDescription>Choose your preferred appearance</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {[
              { value: 'light', label: 'Light', icon: Sun },
              { value: 'dark', label: 'Dark', icon: Moon },
              { value: 'system', label: 'System', icon: Monitor },
            ].map((option) => (
              <Button
                key={option.value}
                variant="outline"
                size="sm"
                onClick={() => setTheme(option.value)}
                className={cn(
                  'gap-2 flex-1',
                  theme === option.value && 'border-primary bg-primary/5 text-primary'
                )}
              >
                <option.icon className="h-4 w-4" />
                {option.label}
                {theme === option.value && <Check className="h-3 w-3 ml-auto" />}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Timezone */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Timezone</CardTitle>
          <CardDescription>Used for displaying dates and scheduling</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Select value={timezone} onValueChange={handleTimezoneChange} disabled={savingTimezone}>
              <SelectTrigger className="w-full max-w-xs">
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
              <SelectContent>
                {COMMON_TIMEZONES.map((tz) => (
                  <SelectItem key={tz.value} value={tz.value}>
                    {tz.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {savingTimezone && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
