"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { TaskStatus } from "@/lib/api/types";

const STATUS_OPTIONS: { value: TaskStatus | ""; label: string }[] = [
  { value: "", label: "Все статусы" },
  { value: "created", label: "Создана" },
  { value: "queued", label: "В очереди" },
  { value: "validating", label: "Проверяется" },
  { value: "processing", label: "Обработка" },
  { value: "completed", label: "Выполнена" },
  { value: "failed", label: "Ошибка" },
];

const LIMIT_OPTIONS = [10, 20, 50, 100];

export function TaskFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const currentStatus = searchParams.get("status") ?? "";
  const currentLimit = searchParams.get("limit") ?? "20";

  function navigate(status: string, limit: string) {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    params.set("limit", limit);
    params.set("offset", "0");
    router.push(`/tasks?${params.toString()}`);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <label htmlFor="status-filter" className="text-sm text-muted-foreground whitespace-nowrap">
          Статус
        </label>
        <select
          id="status-filter"
          value={currentStatus}
          onChange={(e) => navigate(e.target.value, currentLimit)}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="limit-filter" className="text-sm text-muted-foreground whitespace-nowrap">
          На странице
        </label>
        <select
          id="limit-filter"
          value={currentLimit}
          onChange={(e) => navigate(currentStatus, e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {LIMIT_OPTIONS.map((n) => (
            <option key={n} value={String(n)}>
              {n}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
