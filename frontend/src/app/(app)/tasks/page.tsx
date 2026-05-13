import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import { serverFetch } from "@/lib/api/server";
import { TaskStatusBadge } from "@/components/tasks/TaskStatusBadge";
import { TaskFilters } from "./TaskFilters";
import { formatDate } from "@/lib/format";
import type { TasksListResponse, TaskStatus } from "@/lib/api/types";

export const metadata: Metadata = { title: "Документы · DocForge" };

interface SearchParams {
  status?: string;
  limit?: string;
  offset?: string;
}

function buildUrl(params: Record<string, string>) {
  const qs = new URLSearchParams(params);
  return `/tasks?${qs.toString()}`;
}

export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  const status = (params.status ?? "") as TaskStatus | "";
  const limit = Math.min(Math.max(parseInt(params.limit ?? "20", 10), 1), 100);
  const offset = Math.max(parseInt(params.offset ?? "0", 10), 0);

  const data = await serverFetch<TasksListResponse>("/tasks", {
    params: {
      limit,
      offset,
      ...(status ? { status } : {}),
    },
  }).catch(() => null);

  const tasks = data?.items ?? [];
  const hasPrev = offset > 0;
  const hasNext = tasks.length === limit;

  const paginationParams = (newOffset: number) =>
    buildUrl({
      ...(status ? { status } : {}),
      limit: String(limit),
      offset: String(newOffset),
    });

  return (
    <div className="flex flex-col h-full">
      {/* Заголовок */}
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Документы</h1>
        <Link
          href="/predict"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Новая обработка
        </Link>
      </header>

      <div className="flex flex-col gap-4 p-6 flex-1 overflow-y-auto">
        {/* Фильтры */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <Suspense fallback={<div className="h-9 w-72 animate-pulse rounded-md bg-muted" />}>
            <TaskFilters />
          </Suspense>

          {data && tasks.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Показано {offset + 1}–{offset + tasks.length}
              {status ? ` · фильтр: ${status}` : ""}
            </p>
          )}
        </div>

        {/* Ошибка загрузки */}
        {!data && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-6 text-center">
            <p className="text-sm font-medium text-destructive">Не удалось загрузить список задач</p>
            <p className="mt-1 text-xs text-muted-foreground">Обновите страницу или повторите позже</p>
          </div>
        )}

        {/* Пустое состояние */}
        {data && tasks.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-border bg-card py-16 text-center">
            <p className="text-sm font-medium text-foreground">
              {status ? `Задач со статусом «${status}» нет` : "Задач пока нет"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {status
                ? "Попробуйте выбрать другой статус"
                : "Загрузите первый документ, чтобы начать"}
            </p>
            {!status && (
              <Link
                href="/predict"
                className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
              >
                Загрузить документ
              </Link>
            )}
          </div>
        )}

        {/* Список задач */}
        {tasks.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {/* Шапка таблицы */}
            <div className="grid grid-cols-[140px_minmax(0,1fr)_120px_80px_72px] gap-x-4 border-b border-border bg-muted/40 px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              <span>Дата</span>
              <span>Файл / ID</span>
              <span>Статус</span>
              <span>Backend</span>
              <span className="text-right">Кредиты</span>
            </div>

            <ul className="divide-y divide-border">
              {tasks.map((task) => (
                <li key={task.id}>
                  <Link
                    href={`/tasks/${task.id}`}
                    className="grid grid-cols-[140px_minmax(0,1fr)_120px_80px_72px] items-center gap-x-4 px-4 py-3 transition-colors hover:bg-accent/50"
                  >
                    {/* Дата */}
                    <span className="text-xs text-muted-foreground">
                      {formatDate(task.created_at)}
                    </span>

                    {/* Файл / ID */}
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {task.first_document_name ?? task.id}
                      </p>
                      <p className="truncate font-mono text-xs text-primary/70">
                        {task.id}
                      </p>
                    </div>

                    {/* Статус */}
                    <TaskStatusBadge status={task.status} />

                    {/* Backend */}
                    <span className="text-xs text-muted-foreground">{task.backend_name}</span>

                    {/* Кредиты */}
                    <span className="text-right text-xs text-muted-foreground">
                      {task.spent_credits}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Пагинация */}
        {tasks.length > 0 && (
          <div className="flex items-center justify-between">
            {hasPrev ? (
              <Link
                href={paginationParams(offset - limit)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                ← Назад
              </Link>
            ) : (
              <span />
            )}
            {hasNext && (
              <Link
                href={paginationParams(offset + limit)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                Вперёд →
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
