'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { User, Key, Shield, Settings, Monitor } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ProfileSection } from './ProfileSection';
import { PasswordSection } from './PasswordSection';
import { SecuritySection } from './SecuritySection';
import { PreferencesSection } from './PreferencesSection';
import { SessionsSection } from './SessionsSection';

const menuItems = [
  { id: 'profile', label: 'Profile', icon: User, description: 'Personal details' },
  { id: 'password', label: 'Password', icon: Key, description: 'Update credentials' },
  { id: 'security', label: 'Security', icon: Shield, description: 'Two-factor auth' },
  { id: 'preferences', label: 'Preferences', icon: Settings, description: 'Theme & timezone' },
  { id: 'sessions', label: 'Sessions', icon: Monitor, description: 'Active sessions' },
];

export function UserSettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeSection, setActiveSection] = useState('profile');

  useEffect(() => {
    const section = searchParams.get('section');
    if (section && menuItems.some((m) => m.id === section)) {
      setActiveSection(section);
    }
  }, [searchParams]);

  const handleSectionChange = (section: string) => {
    setActiveSection(section);
    router.push(`/app/user-settings?section=${section}`, { scroll: false });
  };

  const active = menuItems.find((m) => m.id === activeSection);

  return (
    <div className="max-w-6xl mx-auto space-y-10">
      {/* Header */}
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Account
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Settings
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Manage your profile, security, and account preferences.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-10">
        {/* Sidebar */}
        <aside className="lg:w-60 flex-shrink-0">
          <nav className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-visible -mx-2 lg:mx-0 px-2 lg:px-0 pb-2 lg:pb-0">
            {menuItems.map((item) => {
              const isActive = activeSection === item.id;
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => handleSectionChange(item.id)}
                  className={cn(
                    'group flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-colors text-left',
                    isActive
                      ? 'bg-primary-soft text-primary'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  )}
                >
                  <Icon
                    className={cn(
                      'h-4 w-4 flex-shrink-0',
                      isActive ? 'text-primary' : 'text-muted-foreground/80 group-hover:text-foreground'
                    )}
                  />
                  <span className="flex-1">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Content */}
        <div className="flex-1 min-w-0 space-y-6">
          {active && (
            <div className="space-y-1 pb-2 border-b border-border">
              <h2 className="text-base font-semibold text-foreground">{active.label}</h2>
              <p className="text-xs text-muted-foreground">{active.description}</p>
            </div>
          )}

          {activeSection === 'profile' && <ProfileSection />}
          {activeSection === 'password' && <PasswordSection />}
          {activeSection === 'security' && <SecuritySection />}
          {activeSection === 'preferences' && <PreferencesSection />}
          {activeSection === 'sessions' && <SessionsSection />}
        </div>
      </div>
    </div>
  );
}
