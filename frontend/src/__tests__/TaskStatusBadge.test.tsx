import { render, screen } from "@testing-library/react";
import { TaskStatusBadge } from "@/components/tasks/TaskStatusBadge";
import type { TaskStatus } from "@/lib/api/types";

const STATUS_LABELS: Record<TaskStatus, string> = {
  created: "Создана",
  queued: "В очереди",
  validating: "Проверяется",
  processing: "Обработка",
  completed: "Выполнена",
  failed: "Ошибка",
};

describe("TaskStatusBadge", () => {
  Object.entries(STATUS_LABELS).forEach(([status, label]) => {
    it(`renders label for status "${status}"`, () => {
      render(<TaskStatusBadge status={status as TaskStatus} />);
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it("applies completed class for completed status", () => {
    const { container } = render(<TaskStatusBadge status="completed" />);
    const badge = container.firstChild as HTMLElement;
    expect(badge.className).toMatch(/green/);
  });

  it("applies destructive-related class for failed status", () => {
    const { container } = render(<TaskStatusBadge status="failed" />);
    const badge = container.firstChild as HTMLElement;
    // bg-destructive/10 text-destructive
    expect(badge.className).toMatch(/destructive/);
  });
});
