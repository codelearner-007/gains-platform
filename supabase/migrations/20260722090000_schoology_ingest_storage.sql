-- Migration: schoology-ingest storage bucket (scraper → backend ingestion landing zone)
-- Inverts the school-logos precedent (20260618000000_school_logos_storage.sql):
-- that bucket is PUBLIC-read for browser <img> tags; this one is PRIVATE because
-- it holds raw Schoology CSV exports containing student PII.

-- Create the schoology-ingest storage bucket (PRIVATE, 50MB limit, any MIME).
--
--   public = false        → deny-all to anon/authenticated (no bucket is public
--                           without a matching storage.objects SELECT policy, and
--                           we deliberately grant none here — see below).
--   file_size_limit       → 50 MiB (52428800), well above logos' 2 MB: student-
--                           submission CSVs for large sections dwarf a logo.
--   allowed_mime_types    → NULL (unrestricted). Schoology exports arrive as
--                           text/csv, but the browser/scraper content-type is not
--                           load-bearing to the parser (which reads raw bytes), so
--                           we do not constrain it at the storage layer.
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES (
  'schoology-ingest',
  'schoology-ingest',
  false,
  52428800
)
ON CONFLICT (id) DO NOTHING;

-- RLS policy for the schoology-ingest bucket.
--
-- Reads/Writes: NONE granted here. This is the inverse of the school-logos
-- bucket, which grants a public SELECT policy for browser embedding. This
-- bucket holds student PII and is touched ONLY server-side by the FastAPI
-- backend (SupabaseStorageBlobClient) and the scraper, both using the
-- service-role key, which bypasses storage RLS entirely. Granting ANY
-- SELECT/INSERT/UPDATE/DELETE to anon/authenticated would leak per-student
-- assessment exports and violate least privilege (CLAUDE.md mistake #14), so we
-- deliberately omit every policy → the bucket is deny-all to non-service-role.
