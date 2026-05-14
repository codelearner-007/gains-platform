import { Skeleton } from '@/components/ui/skeleton';

export default function LoadingState({ label }: { label?: string }) {
  return (
    <div className="w-full flex justify-center">
      <div
        className="bg-[#CACEDA] p-3 shadow-md w-full"
        style={{ maxWidth: 1280 }}
      >
        {label && (
          <div className="px-2 py-1 text-xs text-neutral-700">{label}</div>
        )}
        <Skeleton className="h-20 w-full mb-2" />
        <div className="grid grid-cols-12 gap-2 mb-2">
          <Skeleton className="col-span-3 h-24" />
          <Skeleton className="col-span-9 h-24" />
        </div>
        <Skeleton className="h-8 w-full mb-1" />
        <div className="grid grid-cols-2 gap-2 mb-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
        <Skeleton className="h-72 w-full" />
      </div>
    </div>
  );
}
