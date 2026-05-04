-- Migration: Add user preferences columns and avatars storage bucket
-- Phase 10: User Settings and Admin Extensions

-- Add timezone column to user_profiles
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';
COMMENT ON COLUMN public.user_profiles.timezone IS 'User preferred timezone (IANA format, e.g. America/New_York)';

-- Add preferences JSONB column to user_profiles
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';
COMMENT ON COLUMN public.user_profiles.preferences IS 'User preferences as JSON (default_view, notification settings, etc.)';

-- Create avatars storage bucket (public, 2MB limit, image types only)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'avatars',
  'avatars',
  true,
  2097152,
  ARRAY['image/jpeg','image/png','image/gif','image/webp']
)
ON CONFLICT (id) DO NOTHING;

-- RLS policies for avatars bucket

-- Users can upload their own avatar (folder must match their user ID)
CREATE POLICY users_upload_own_avatar ON storage.objects
  FOR INSERT
  WITH CHECK (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);

-- Users can update their own avatar
CREATE POLICY users_update_own_avatar ON storage.objects
  FOR UPDATE
  USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);

-- Users can delete their own avatar
CREATE POLICY users_delete_own_avatar ON storage.objects
  FOR DELETE
  USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);

-- Anyone can read avatars (public bucket)
CREATE POLICY public_avatar_read ON storage.objects
  FOR SELECT
  USING (bucket_id = 'avatars');
