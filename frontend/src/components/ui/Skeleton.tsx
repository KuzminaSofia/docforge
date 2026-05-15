import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function SkeletonPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-8 w-28" />
      </div>
      <div className="flex flex-col gap-4 p-6">
        <div className="flex gap-3">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="h-9 w-24" />
        </div>
        <div className="overflow-hidden rounded-xl border border-border">
          <div className="border-b border-border bg-muted/40 px-4 py-2.5">
            <Skeleton className="h-3 w-64" />
          </div>
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 border-b border-border px-4 py-3 last:border-0">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function SkeletonDashboard() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-9 w-36" />
      </div>
      <div className="rounded-xl border border-border bg-card p-6 space-y-4">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-2 flex-1">
            <Skeleton className="h-3 w-28" />
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-4 w-96" />
          </div>
          <Skeleton className="h-20 w-28 shrink-0" />
        </div>
        <div className="flex gap-3">
          <Skeleton className="h-9 w-36" />
          <Skeleton className="h-9 w-36" />
          <Skeleton className="h-9 w-36" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-6 space-y-3">
          <Skeleton className="h-4 w-20" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex justify-between">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-32" />
            </div>
          ))}
        </div>
        <div className="rounded-xl border border-border bg-card p-6 space-y-3">
          <Skeleton className="h-4 w-32" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-3 px-2 py-1.5">
              <div className="space-y-1 flex-1">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-24" />
              </div>
              <Skeleton className="h-5 w-20" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
