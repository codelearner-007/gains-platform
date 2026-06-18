-- Migration: school-logos storage bucket (per-school logo upload)
-- Mirrors the avatars bucket precedent (20260201000009_user_preferences.sql).
-- Logos render in dashboard/report headers as raw <img src> / unoptimized
-- next/image, so the bucket MUST be public-read.

-- Create the school-logos storage bucket (public, 2MB limit, raster image types).
-- SVG is intentionally excluded (inline-SVG XSS risk), matching the avatars bucket.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'school-logos',
  'school-logos',
  true,
  2097152,
  ARRAY['image/jpeg','image/png','image/gif','image/webp']
)
ON CONFLICT (id) DO NOTHING;

-- RLS policy for the school-logos bucket.
--
-- Reads: public (logos are embedded in browser <img> tags with no auth header).
-- Writes: NONE granted here. Uploads are performed server-side by the FastAPI
-- backend using the service-role key, which bypasses storage RLS. Granting
-- INSERT/UPDATE/DELETE to anon/authenticated would violate least privilege
-- (CLAUDE.md mistake #14), so we deliberately omit write policies.
--
-- Idempotent (DROP IF EXISTS then CREATE) so `supabase db push` is re-runnable,
-- following the convention in 20260617120000_*.sql.
DROP POLICY IF EXISTS public_school_logo_read ON storage.objects;
CREATE POLICY public_school_logo_read ON storage.objects
  FOR SELECT
  USING (bucket_id = 'school-logos');
