import { cn } from "@/lib/utils";
import type { TaskStatus } from "@/lib/api/types";

const STATUS_CONFIG: Record<TaskStatus, { label: string; className: string }> = {
  created: {
    label: "Создана",
    className: "bg-secondary text-secondary-foreground",
  },
  queued: {
    label: "В очереди",
    className: "bg-amber-100 text-amber-800",
  },
  validating: {
    label: "Проверяется",
    className: "bg-blue-100 text-blue-800",
  },
  processing: {
    label: "Обработка",
    className: "bg-indigo-100 text-indigo-800",
  },
  completed: {
    label: "Выполнена",
    className: "bg-green-100 text-green-800",
  },
  failed: {
    label: "Ошибка",
    className: "bg-destructive/10 text-destructive",
  },
};

interface TaskStatusBadgeProps {
  status: TaskStatus;
  className?: string;
}

export function TaskStatusBadge({ status, className }: TaskStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
