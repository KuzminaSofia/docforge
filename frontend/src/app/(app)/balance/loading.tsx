import { Skeleton } from "@/components/ui/Skeleton";

export default function BalanceLoading() {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-8 w-24" />
      </div>
      <div className="flex flex-col gap-6 p-6 max-w-2xl">
        <Skeleton className="h-4 w-full" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-border bg-card p-6 space-y-3">
            <Skeleton className="h-3 w-28" />
            <Skeleton className="h-10 w-24" />
            <Skeleton className="h-3 w-16" />
          </div>
          <div className="rounded-xl border border-border bg-card p-6 space-y-3">
            <Skeleton className="h-3 w-28" />
            <div className="grid grid-cols-4 gap-1.5">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-8" />
              ))}
            </div>
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
          </div>
        </div>
      </div>
    </div>
  );
}
