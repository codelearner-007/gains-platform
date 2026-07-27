"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Home, User, Menu, X, LogOut, Key, Shield } from 'lucide-react';
import { useGlobal } from '@/lib/context/GlobalContext';
import { useAuth } from '@/lib/hooks/useAuth';
import { canSeeAdminEntry } from '@/lib/rbac/access';
import { Button } from '@/components/ui/button';
import SchoolSwitcher from '@/components/app/SchoolSwitcher';
import { BrandWordmark } from '@/components/common/BrandWordmark';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
function getInitials(email: string) {
  const parts = email.split('@')[0].split(/[._-]/);
  return parts.length > 1
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : parts[0].slice(0, 2).toUpperCase();
}

export default function AppLayout({
  children,
  isLtiUser = false,
}: {
  children: React.ReactNode;
  // Schoology-embedded users get a bare, analytics-only shell: Dashboard +
  // reports, and none of the account/settings chrome. Decided server-side (see
  // ProtectedShellLayout) so there is no flash of the full nav on first paint.
  isLtiUser?: boolean;
}) {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const { user, loading } = useGlobal();
  const { logout } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const handleChangePassword = () => {
    router.push('/app/user-settings?section=password');
  };

  const navigation = [
    { name: 'Dashboard', href: '/app', icon: Home },
    // Account/settings is hidden for Schoology-embedded users.
    ...(isLtiUser ? [] : [{ name: 'Settings', href: '/app/user-settings', icon: User }]),
  ];

  const showAdmin = !isLtiUser && user && canSeeAdminEntry({
    permissions: user.app_metadata?.permissions ?? [],
    hierarchy_rank: user.app_metadata?.hierarchy_rank,
    user_role: user.app_metadata?.user_role,
  });

  const toggleSidebar = () => setSidebarOpen((v) => !v);

  return (
    <div className="min-h-screen bg-background">
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-background/80 backdrop-blur-sm z-20 lg:hidden"
          onClick={toggleSidebar}
        />
      )}

      <aside
        className={`print:hidden fixed inset-y-0 left-0 w-64 bg-card border-r border-border flex flex-col transform transition-transform duration-200 ease-in-out z-30
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
      >
        <div className="h-16 flex items-center justify-between px-5 border-b border-border flex-shrink-0">
          <Link href="/app" className="flex items-center" aria-label="GAINS home">
            <BrandWordmark height={24} priority />
          </Link>
          <Button
            onClick={toggleSidebar}
            variant="ghost"
            size="icon"
            className="lg:hidden h-8 w-8"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {!isLtiUser && (
            <div className="px-1 pb-3">
              <SchoolSwitcher />
            </div>
          )}
          {navigation.map((item) => {
            const isActive =
              item.href === '/app'
                ? pathname === item.href
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setSidebarOpen(false)}
                className={`group flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  isActive
                    ? 'bg-primary-soft text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`}
              >
                <Icon
                  className={`h-4 w-4 ${
                    isActive ? 'text-primary' : 'text-muted-foreground/80 group-hover:text-foreground'
                  }`}
                />
                {item.name}
              </Link>
            );
          })}

          {showAdmin && (
            <>
              <div className="h-px my-3 bg-border" />
              <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
                Administration
              </p>
              <Link
                href="/admin"
                onClick={() => setSidebarOpen(false)}
                className={`group flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  pathname.startsWith('/admin')
                    ? 'bg-primary-soft text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`}
              >
                <Shield
                  className={`h-4 w-4 ${
                    pathname.startsWith('/admin') ? 'text-primary' : 'text-muted-foreground/80 group-hover:text-foreground'
                  }`}
                />
                Admin Panel
              </Link>
            </>
          )}
        </nav>

        {!isLtiUser && (
        <div className="flex-shrink-0 border-t border-border p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild disabled={loading}>
              <Button variant="ghost" className="w-full justify-start h-auto py-2 px-2 hover:bg-accent">
                {loading ? (
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
                      <span className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-primary" />
                    </span>
                    <span className="text-xs text-muted-foreground">Loading…</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 min-w-0 w-full">
                    <span className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-primary/70 text-primary-foreground flex items-center justify-center flex-shrink-0 text-xs font-semibold">
                      {user ? getInitials(user.email) : '??'}
                    </span>
                    <span className="flex-1 text-left min-w-0">
                      <p className="text-xs font-medium text-foreground truncate">
                        {user?.email?.split('@')[0] || 'Guest'}
                      </p>
                      <p className="text-[11px] text-muted-foreground truncate">
                        {user?.email || ''}
                      </p>
                    </span>
                  </div>
                )}
              </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent side="top" align="start" className="w-56">
              <DropdownMenuLabel className="space-y-1">
                <p className="text-xs text-muted-foreground font-normal">Signed in as</p>
                <p className="text-sm font-medium truncate">{user?.email}</p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={handleChangePassword}>
                <Key className="text-muted-foreground" />
                Change Password
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => void handleLogout()}
                className="text-destructive focus:text-destructive"
              >
                <LogOut className="text-destructive/80" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        )}
      </aside>

      <div className="lg:pl-64 print:pl-0 min-h-screen flex flex-col">
        <div className="sticky top-0 z-10 flex items-center h-14 px-4 lg:hidden print:hidden surface-blur bg-background/80 border-b border-border">
          <Button
            onClick={toggleSidebar}
            variant="ghost"
            size="icon"
            aria-label="Open sidebar"
            className="h-8 w-8"
          >
            <Menu className="h-4 w-4" />
          </Button>
        </div>

        <main className="flex-1 p-6 lg:p-10">{children}</main>
      </div>
    </div>
  );
}
