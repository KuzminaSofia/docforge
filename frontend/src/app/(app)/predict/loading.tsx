import { Skeleton } from "@/components/ui/Skeleton";

export default function PredictLoading() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-8 w-28" />
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col gap-4 p-6">
          <Skeleton className="h-44 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-lg" />
        </div>
        <div className="w-80 shrink-0 border-l border-border p-6 space-y-4">
          <div className="space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-9 w-full" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-9 w-full" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-9 w-full" />
          </div>
          <Skeleton className="h-20 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-9 w-full" />
        </div>
      </div>
    </div>
  );
}
