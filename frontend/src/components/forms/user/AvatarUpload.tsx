'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import Image from 'next/image';
import { Upload, Loader2 } from 'lucide-react';
import { profileService } from '@/lib/services/profile.service';

interface AvatarUploadProps {
  currentAvatarUrl: string | null;
  onUploaded: (url: string) => void;
}

export function AvatarUpload({ currentAvatarUrl, onUploaded }: AvatarUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(currentAvatarUrl);

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
        const result = await profileService.uploadAvatar(file);
        setPreviewUrl(result.avatar_url);
        onUploaded(result.avatar_url);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
        setPreviewUrl(currentAvatarUrl);
      } finally {
        setUploading(false);
        URL.revokeObjectURL(localPreview);
      }
    },
    [currentAvatarUrl, onUploaded]
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
              alt="Avatar preview"
              width={64}
              height={64}
              unoptimized
              className="w-16 h-16 rounded-full object-cover border border-border"
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

      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
