'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import Image from 'next/image';
import { Upload, Loader2 } from 'lucide-react';
import { uploadSchoolLogo } from '@/lib/services/schools.service';

interface SchoolLogoUploadProps {
  schoolId: string;
  currentLogoUrl: string | null;
  onUploaded: (url: string) => void;
}

/**
 * Per-school logo uploader. Mirrors AvatarUpload but renders the preview in a
 * square (object-contain) box rather than a circle, and persists via the
 * schools logo endpoint. The upload is self-contained: it persists immediately
 * server-side and is independent of the surrounding edit form's Save button.
 */
export function SchoolLogoUpload({
  schoolId,
  currentLogoUrl,
  onUploaded,
}: SchoolLogoUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(currentLogoUrl);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;

      setError(null);
      setUploading(true);

      // Show local preview immediately
      const localPreview = URL.createObjectURL(file);
      setPreviewUrl(localPreview);

      try {
        const school = await uploadSchoolLogo(schoolId, file);
        const url = school.logo_url;
        if (url) {
          setPreviewUrl(url);
          onUploaded(url);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
        setPreviewUrl(currentLogoUrl);
      } finally {
        setUploading(false);
        URL.revokeObjectURL(localPreview);
      }
    },
    [schoolId, currentLogoUrl, onUploaded]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpg', '.jpeg', '.png', '.gif', '.webp'] },
    maxSize: 2 * 1024 * 1024,
    multiple: false,
    onDropRejected: (rejections) => {
      const rejection = rejections[0];
      if (rejection?.errors[0]?.code === 'file-too-large') {
        setError('File must be under 2MB');
      } else if (rejection?.errors[0]?.code === 'file-invalid-type') {
        setError('Only image files are allowed');
      } else {
        setError('Invalid file');
      }
    },
  });

  return (
    <div className="space-y-2">
      <div
        {...getRootProps()}
        className={`relative flex flex-col items-center justify-center gap-2 p-4 border-2 border-dashed rounded-lg cursor-pointer transition-colors ${
          isDragActive
            ? 'border-primary bg-primary/5'
            : 'border-border hover:border-primary/50'
        }`}
      >
        <input {...getInputProps()} />

        {uploading ? (
          <div className="flex flex-col items-center gap-2 py-2">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="text-sm text-muted-foreground">Uploading...</span>
          </div>
        ) : previewUrl ? (
          <div className="flex items-center gap-4">
            <Image
              src={previewUrl}
              alt="School logo preview"
              width={80}
              height={80}
              unoptimized
              className="h-20 w-20 rounded-md object-contain border border-border bg-background p-1"
            />
            <div className="text-sm text-muted-foreground">
              <p>Drop a new image or click to change</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-2">
            <Upload className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {isDragActive ? 'Drop image here' : 'Drop an image or click to upload'}
            </p>
          </div>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        JPG, PNG, GIF, or WebP. Max 2MB.
      </p>

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
