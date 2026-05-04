'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useGlobal } from '@/lib/context/GlobalContext';
import { useUser } from '@/lib/hooks/useUser';
import { ProfileForm } from '@/components/forms/user/ProfileForm';
import { AvatarUpload } from '@/components/forms/user/AvatarUpload';
import {
  CheckCircle,
  Edit2,
} from 'lucide-react';
import type { UserProfileInput } from '@/lib/schemas/user.schema';

export function ProfileSection() {
  const { user, refreshUser } = useGlobal();
  const { profile, fetchProfile, updateProfile, loading } = useUser();
  const [isEditing, setIsEditing] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (data: UserProfileInput) => {
    const result = await updateProfile(data);
    if (result.success) {
      setSuccess(true);
      setIsEditing(false);
      setTimeout(() => setSuccess(false), 5000);
      await refreshUser();
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
  };

  const formatDate = (date?: Date) => {
    if (!date) return 'N/A';
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const roleName = user?.app_metadata?.user_role;

  return (
    <div className="space-y-6">
      {success && (
        <Alert className="border-primary/30 bg-primary/5 text-primary">
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>
            Profile updated successfully!
          </AlertDescription>
        </Alert>
      )}

      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              {profile?.avatar_url ? (
                <Image
                  src={profile.avatar_url}
                  alt="Profile"
                  width={80}
                  height={80}
                  unoptimized
                  className="w-20 h-20 rounded-full object-cover border-2 border-border"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center border-2 border-border">
                  <span className="text-2xl text-primary font-semibold">
                    {user?.email ? user.email.charAt(0).toUpperCase() : '?'}
                  </span>
                </div>
              )}
              <div>
                <CardTitle className="text-xl">{profile?.full_name || 'Unnamed User'}</CardTitle>
                <CardDescription className="mt-1">{user?.email}</CardDescription>
                <div className="flex items-center gap-2 mt-2">
                  {roleName && (
                    <Badge variant="secondary" className="text-xs capitalize font-normal">
                      {roleName.replace('_', ' ')}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            {!isEditing && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsEditing(true)}
                className="gap-2"
              >
                <Edit2 className="h-3.5 w-3.5" />
                Edit Profile
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isEditing ? (
            <div className="pt-4 border-t border-border/50 space-y-6">
              <div>
                <h3 className="text-sm font-medium mb-2">Profile Photo</h3>
                <AvatarUpload
                  currentAvatarUrl={profile?.avatar_url || null}
                  onUploaded={async () => {
                    await fetchProfile();
                    await refreshUser();
                  }}
                />
              </div>
              <ProfileForm
                defaultValues={{
                  full_name: profile?.full_name || '',
                  avatar_url: profile?.avatar_url || '',
                  department: profile?.department || '',
                }}
                onSubmit={handleSubmit}
                onCancel={handleCancel}
                loading={loading}
              />
            </div>
          ) : (
            <div className="grid gap-6 sm:grid-cols-2 pt-2">
              <div className="space-y-1">
                <div className="text-sm font-medium text-muted-foreground">Full Name</div>
                <div className="text-sm font-medium">{profile?.full_name || 'Not set'}</div>
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium text-muted-foreground">Email Address</div>
                <div className="text-sm font-medium">{user?.email || 'Not set'}</div>
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium text-muted-foreground">Department</div>
                <div className="text-sm font-medium">{profile?.department || 'Not set'}</div>
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium text-muted-foreground">Member Since</div>
                <div className="text-sm font-medium">{formatDate(user?.registered_at)}</div>
              </div>
              <div className="space-y-1 sm:col-span-2">
                <div className="text-sm font-medium text-muted-foreground">User ID</div>
                <div className="text-sm font-mono bg-muted/50 p-2 rounded border border-border/50 inline-block">
                  {user?.id || 'N/A'}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
