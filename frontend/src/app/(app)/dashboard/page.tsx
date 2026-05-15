import Link from "next/link";
import type { Metadata } from "next";
import { getRequiredUser } from "@/lib/auth";
import { serverFetch } from "@/lib/api/server";
import { formatDateLong } from "@/lib/format";
import { TaskStatusBadge } from "@/components/tasks/TaskStatusBadge";
import type { TasksListResponse } from "@/lib/api/types";

export const metadata: Metadata = { title: "Кабинет · DocForge" };

const ROLE_LABELS: Record<string, string> = {
  user: "Пользователь",
  admin: "Администратор",
};

export default async function DashboardPage() {
  const [user, tasksResult] = await Promise.all([
    getRequiredUser(),
    serverFetch<TasksListResponse>("/tasks", { params: { limit: 5, offset: 0 } }).catch(
      () => null,
    ),
  ]);

  const recentTasks = tasksResult?.items ?? [];

  return (
    <div className="p-8 space-y-6">
      {/* Заголовок страницы */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Кабинет</h1>
        <Link
          href="/predict"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Новая обработка
        </Link>
      </div>

      {/* Hero: приветствие + баланс */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Личный кабинет
            </p>
            <h2 className="mt-1 text-xl font-semibold text-foreground">
              Здравствуйте, {user.email}
            </h2>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Загрузите технический документ, дождитесь обработки и получите
              структурированный результат в формате JSON, Markdown или текста.
            </p>
          </div>
          <div className="shrink-0 rounded-lg border border-border bg-muted/40 px-5 py-4 text-center">
            <p className="text-xs font-medium text-muted-foreground">Баланс</p>
            <p className="mt-0.5 text-2xl font-bold text-foreground">{user.balance_credits}</p>
            <p className="text-xs text-muted-foreground">кредитов</p>
          </div>
        </div>

        {/* Быстрые действия */}
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href="/predict"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Запустить обработку
          </Link>
          <Link
            href="/tasks"
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Открыть документы
          </Link>
          <Link
            href="/history"
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            История операций
          </Link>
        </div>
      </div>

      {/* Сетка: аккаунт + последние задачи */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Аккаунт */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-semibold text-foreground">Аккаунт</h3>
          <dl className="space-y-3">
            <div className="flex items-center justify-between">
              <dt className="text-sm text-muted-foreground">Email</dt>
              <dd className="text-sm font-medium text-foreground">{user.email}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-sm text-muted-foreground">Роль</dt>
              <dd className="text-sm font-medium text-foreground">
                {ROLE_LABELS[user.role] ?? user.role}
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-sm text-muted-foreground">Статус</dt>
              <dd className="text-sm font-medium text-foreground">
                {user.is_active ? (
                  <span className="text-green-600">Активен</span>
                ) : (
                  <span className="text-destructive">Неактивен</span>
                )}
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-sm text-muted-foreground">Участник с</dt>
              <dd className="text-sm font-medium text-foreground">{formatDateLong(user.created_at)}</dd>
            </div>
          </dl>
        </div>

        {/* Последние задачи */}
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Последние задачи</h3>
            <Link href="/tasks" className="text-xs text-primary hover:underline">
              Все задачи →
            </Link>
          </div>

          {recentTasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <p className="text-sm text-muted-foreground">Задач пока нет</p>
              <Link
                href="/predict"
                className="mt-3 text-sm font-medium text-primary hover:underline"
              >
                Загрузить первый документ
              </Link>
            </div>
          ) : (
            <ul className="space-y-3">
              {recentTasks.map((task) => (
                <li key={task.id}>
                  <Link
                    href={`/tasks/${task.id}`}
                    className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 transition-colors hover:bg-accent"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {task.first_document_name ?? `Задача ${task.id.slice(0, 8)}`}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDateLong(task.created_at)}
                      </p>
                    </div>
                    <TaskStatusBadge status={task.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
