'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Menu, X, Shield, Users, FileText, LogOut, Key, ArrowLeft, Settings, LayoutGrid, School } from 'lucide-react';
import { BrandWordmark } from '@/components/common/BrandWordmark';
import { useGlobal } from '@/lib/context/GlobalContext';
import { useAuth } from '@/lib/hooks/useAuth';
import { getAccessibleAdminModules } from '@/lib/rbac/access';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
const moduleIcons = {
  rbac: Shield,
  users: Users,
  audit: FileText,
  schools: School,
} as const;

type NavItem = {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
};

function getInitials(email: string) {
  const parts = email.split('@')[0].split(/[._-]/);
  return parts.length > 1
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : parts[0].slice(0, 2).toUpperCase();
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const { user, loading } = useGlobal();
  const { logout } = useAuth();
  const claims = useAdminClaims();

  const navigation = useMemo<NavItem[]>(() => {
    const modules = getAccessibleAdminModules(claims);
    return [
      { name: 'Overview', href: '/admin', icon: LayoutGrid },
      ...modules.map((m) => ({
        name: m.name,
        href: `/admin/${m.key}`,
        icon: moduleIcons[m.key as keyof typeof moduleIcons] ?? Shield,
      })),
    ];
  }, [claims]);

  const toggleSidebar = () => setSidebarOpen((v) => !v);

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const handleChangePassword = () => {
    router.push('/app/user-settings');
  };

  return (
    <div className="min-h-screen bg-background flex">
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-background/80 backdrop-blur-sm z-20 lg:hidden"
          onClick={toggleSidebar}
        />
      )}

      <aside
        className={`w-64 bg-card border-r border-border flex-shrink-0 flex flex-col
        ${isSidebarOpen ? 'fixed inset-y-0 left-0 z-30' : 'hidden'} lg:flex`}
      >
        <div className="h-16 flex items-center gap-2 px-5 border-b border-border">
          <Button asChild variant="ghost" size="icon" className="h-8 w-8 -ml-1">
            <Link href="/app" aria-label="Back to app">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div className="flex items-center gap-2 min-w-0">
            <BrandWordmark height={22} priority />
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground border-l border-border pl-2">
              Admin
            </span>
          </div>
          <Button
            onClick={toggleSidebar}
            variant="ghost"
            size="icon"
            className="lg:hidden ml-auto h-8 w-8"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
          <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
            Access Control
          </p>
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
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
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild disabled={loading}>
              <Button variant="ghost" className="w-full h-auto flex items-center gap-3 p-2 rounded-md hover:bg-accent justify-start">
                <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary to-primary/70 text-primary-foreground flex items-center justify-center flex-shrink-0 text-xs font-semibold">
                  {loading ? '?' : user ? getInitials(user.email) : '??'}
                </div>
                <div className="flex-1 text-left overflow-hidden min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">
                    {loading ? 'Loading…' : user?.email?.split('@')[0] || 'Guest'}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {claims?.user_role === 'super_admin' ? 'Super Admin' : 'Admin'}
                  </p>
                </div>
                <Settings className="h-3.5 w-3.5 text-muted-foreground/70 flex-shrink-0" />
              </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" side="right" className="w-56">
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
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="sticky top-0 z-10 flex items-center h-14 surface-blur bg-background/80 border-b border-border px-4 lg:hidden">
          <Button onClick={toggleSidebar} variant="ghost" size="icon" aria-label="Open sidebar" className="h-8 w-8">
            <Menu className="h-4 w-4" />
          </Button>
        </div>

        <main id="main-content" className="flex-1 p-6 lg:p-10 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
