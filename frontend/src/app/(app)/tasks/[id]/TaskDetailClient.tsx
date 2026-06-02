"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { clientFetch, clientFetchText } from "@/lib/api/client";
import { useTaskSSE } from "@/hooks/useTaskSSE";
import { formatDateTime } from "@/lib/format";
import { TaskStatusBadge } from "@/components/tasks/TaskStatusBadge";
import { cn } from "@/lib/utils";
import type { TaskResultResponse, TaskStatus, ValidationIssueResponse } from "@/lib/api/types";

const TERMINAL_STATUSES: TaskStatus[] = ["completed", "failed"];

const PROCESSING_STEPS: { status: TaskStatus; label: string }[] = [
  { status: "created", label: "Задача создана" },
  { status: "queued", label: "В очереди на обработку" },
  { status: "validating", label: "Проверка документов" },
  { status: "processing", label: "Извлечение данных" },
  { status: "completed", label: "Завершено" },
];

const STATUS_ORDER: Record<TaskStatus, number> = {
  created: 0,
  queued: 1,
  validating: 2,
  processing: 3,
  completed: 4,
  failed: 4,
};

type Tab = "meta" | "artifacts" | "json" | "issues";

interface Props {
  taskId: string;
  initial: TaskResultResponse;
}

export function TaskDetailClient({ taskId, initial }: Props) {
  const router = useRouter();
  const [data, setData] = useState<TaskResultResponse>(initial);
  const [activeTab, setActiveTab] = useState<Tab>("meta");
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [markdownLoading, setMarkdownLoading] = useState(false);

  const status = data.task.status;
  const isTerminal = TERMINAL_STATUSES.includes(status);

  // SSE-стрим статуса — бэкенд пушит изменения, поллинга нет.
  // При терминальном статусе делаем одиночный fetch полного результата.
  useTaskSSE(taskId, !isTerminal, {
    onStatus: (statusData) => {
      setData((prev) => ({
        ...prev,
        task: { ...prev.task, ...statusData },
      }));
    },
    onDone: (statusData) => {
      setData((prev) => ({
        ...prev,
        task: { ...prev.task, ...statusData },
      }));
      clientFetch<TaskResultResponse>(`/tasks/${taskId}/result`)
        .then(setData)
        .catch(() => {});
      // Обновляем серверные компоненты (layout с балансом в UserMenu).
      // Баланс списывается воркером в момент завершения задачи —
      // router.refresh() гарантирует актуальные данные в сайдбаре.
      router.refresh();
    },
  });

  // fetch markdown preview when completed
  useEffect(() => {
    if (status !== "completed") return;
    const md = data.artifacts.find(
      (a) => a.name.endsWith(".md") || a.mime_type === "text/markdown",
    );
    if (!md) return;

    const controller = new AbortController();
    setMarkdownLoading(true);
    clientFetchText(`/tasks/${taskId}/artifacts/${encodeURIComponent(md.name)}`, {
      signal: controller.signal,
    })
      .then((text) => setMarkdownContent(text))
      .catch((err) => { if (err instanceof Error && err.name !== "AbortError") setMarkdownContent(null); })
      .finally(() => setMarkdownLoading(false));

    return () => controller.abort();
  }, [status, taskId, data.artifacts]);

  return (
    <div className="flex flex-col h-full">
      {/* Скрытый регион для уведомлений screen reader при обновлении статуса */}
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {PROCESSING_STEPS.find((s) => s.status === status)?.label ?? status}
      </p>

      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-6 py-4 gap-4 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/tasks"
            className="shrink-0 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Документы
          </Link>
          <span className="text-muted-foreground/50">/</span>
          <h1 className="text-sm font-mono text-muted-foreground truncate">
            {taskId.slice(0, 8)}…
          </h1>
        </div>
        <TaskStatusBadge status={status} />
      </header>

      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Left panel */}
        <div className="flex flex-1 flex-col overflow-hidden p-6 min-h-0">
          {!isTerminal && <ProgressStepper status={status} />}
          {status === "failed" && (
            <ErrorCard
              message={data.task.error_message}
              modelName={data.task.model_name}
              targetSchema={data.task.target_schema}
            />
          )}
          {status === "completed" && (
            <MarkdownPanel
              content={markdownContent}
              loading={markdownLoading}
              hasArtifacts={data.artifacts.length > 0}
            />
          )}
        </div>

        {/* Right panel */}
        <aside className="w-80 shrink-0 border-l border-border flex flex-col overflow-hidden">
          <TabBar active={activeTab} onChange={setActiveTab} issues={data.result?.validation_issues.length ?? 0} />
          <div className="flex-1 overflow-y-auto p-4">
            {activeTab === "meta" && <MetaTab data={data} />}
            {activeTab === "artifacts" && <ArtifactsTab taskId={taskId} artifacts={data.artifacts} />}
            {activeTab === "json" && <JsonTab data={data.result?.extracted_data ?? null} />}
            {activeTab === "issues" && <IssuesTab issues={data.result?.validation_issues ?? []} />}
          </div>
        </aside>
      </div>
    </div>
  );
}

// ── Progress stepper ──────────────────────────────────────────────────────────

function ProgressStepper({ status }: { status: TaskStatus }) {
  const currentOrder = STATUS_ORDER[status] ?? 0;

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <p className="mb-4 text-sm font-medium text-foreground">Обработка…</p>
      <ol className="space-y-3">
        {PROCESSING_STEPS.filter((s) => s.status !== "failed").map((step, i) => {
          const stepOrder = STATUS_ORDER[step.status];
          const done = stepOrder < currentOrder;
          const active = stepOrder === currentOrder;
          return (
            <li key={i} className="flex items-center gap-3">
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                  done && "bg-green-100 text-green-700",
                  active && "bg-primary text-primary-foreground animate-pulse",
                  !done && !active && "bg-muted text-muted-foreground",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "text-sm",
                  active ? "font-medium text-foreground" : "text-muted-foreground",
                )}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ── Error card ────────────────────────────────────────────────────────────────

function ErrorCard({
  message,
  modelName,
  targetSchema,
}: {
  message: string | null;
  modelName: string;
  targetSchema: string | null;
}) {
  const retryParams = new URLSearchParams();
  retryParams.set("model", modelName);
  if (targetSchema) retryParams.set("schema", targetSchema);

  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-6">
      <div className="mb-3 flex items-start justify-between gap-4">
        <p className="text-sm font-semibold text-destructive">Обработка завершилась с ошибкой</p>
        <Link
          href={`/predict?${retryParams.toString()}`}
          className="shrink-0 rounded-md border border-destructive/40 bg-background px-3 py-1 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
        >
          Повторить
        </Link>
      </div>
      {message && <p className="text-xs text-destructive/80 font-mono whitespace-pre-wrap">{message}</p>}
    </div>
  );
}

// ── Markdown panel ────────────────────────────────────────────────────────────

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(getText()).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      onClick={handleCopy}
      className="rounded px-2 py-0.5 text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
    >
      {copied ? "Скопировано!" : "Копировать"}
    </button>
  );
}

function MarkdownPanel({
  content,
  loading,
  hasArtifacts,
}: {
  content: string | null;
  loading: boolean;
  hasArtifacts: boolean;
}) {
  const [view, setView] = useState<"rendered" | "raw">("rendered");

  if (loading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-border bg-card p-10">
        <p className="text-sm text-muted-foreground animate-pulse">Загрузка превью…</p>
      </div>
    );
  }
  if (!content) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card py-16 text-center">
        <p className="text-sm font-medium text-foreground">Markdown-превью недоступно</p>
        {hasArtifacts && (
          <p className="mt-1 text-xs text-muted-foreground">Скачайте артефакты на вкладке справа</p>
        )}
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col flex-1 min-h-0">
      <div className="border-b border-border bg-muted/40 px-4 py-2 shrink-0 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          {(["rendered", "raw"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
                view === v
                  ? "bg-background text-foreground shadow-sm border border-border"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {v === "rendered" ? "Rendered" : "Raw"}
            </button>
          ))}
        </div>
        <CopyButton getText={() => content} />
      </div>
      {view === "rendered" ? (
        <div className="overflow-auto p-4 min-h-0 text-sm text-foreground leading-relaxed [&_h1]:text-xl [&_h1]:font-bold [&_h1]:mb-3 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:mb-2 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mb-1.5 [&_p]:mb-2 [&_ul]:mb-2 [&_ul]:pl-5 [&_ul]:list-disc [&_ol]:mb-2 [&_ol]:pl-5 [&_ol]:list-decimal [&_li]:mb-0.5 [&_strong]:font-semibold [&_em]:italic [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:rounded-lg [&_pre]:overflow-x-auto [&_pre]:mb-2 [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_table]:w-full [&_table]:border-collapse [&_table]:mb-2 [&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:text-xs [&_th]:font-medium [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1 [&_td]:text-xs [&_hr]:border-border [&_hr]:my-3">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      ) : (
        <pre className="overflow-auto p-4 text-xs text-foreground font-mono whitespace-pre-wrap leading-relaxed min-h-0">
          {content}
        </pre>
      )}
    </div>
  );
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: "meta", label: "Задача" },
  { id: "artifacts", label: "Артефакты" },
  { id: "json", label: "JSON" },
  { id: "issues", label: "Замечания" },
];

function TabBar({
  active,
  onChange,
  issues,
}: {
  active: Tab;
  onChange: (t: Tab) => void;
  issues: number;
}) {
  return (
    <div className="flex border-b border-border">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "flex-1 px-2 py-2.5 text-xs font-medium transition-colors relative",
            active === tab.id
              ? "text-foreground after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
          {tab.id === "issues" && issues > 0 && (
            <span className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-amber-100 text-[10px] font-semibold text-amber-700">
              {issues}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── Meta tab ──────────────────────────────────────────────────────────────────

function formatDuration(startedAt: string | null, completedAt: string | null): string | null {
  if (!startedAt || !completedAt) return null;
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs} с`;
  const mins = Math.floor(secs / 60);
  return `${mins} мин ${secs % 60} с`;
}

function MetaTab({ data }: { data: TaskResultResponse }) {
  const { task } = data;
  const duration = formatDuration(task.started_at, task.completed_at);
  const rows: { label: string; value: string | null | undefined }[] = [
    { label: "ID задачи", value: task.id },
    { label: "Статус", value: task.status },
    { label: "Модель", value: task.model_name },
    { label: "Backend", value: task.backend_name },
    { label: "Схема", value: task.target_schema },
    { label: "Кредиты", value: String(task.spent_credits) },
    { label: "Создана", value: task.created_at ? formatDateTime(task.created_at) : null },
    { label: "Старт", value: task.started_at ? formatDateTime(task.started_at) : null },
    { label: "Завершена", value: task.completed_at ? formatDateTime(task.completed_at) : null },
    { label: "Время обработки", value: duration },
  ];

  return (
    <dl className="space-y-3">
      {rows.map(({ label, value }) => (
        <div key={label}>
          <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</dt>
          <dd className="mt-0.5 text-sm text-foreground font-mono break-all">
            {value ?? <span className="text-muted-foreground">—</span>}
          </dd>
        </div>
      ))}

      {task.documents.length > 0 && (
        <div>
          <dt className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
            Документы ({task.documents.length})
          </dt>
          <ul className="space-y-1">
            {task.documents.map((doc) => (
              <li key={doc.id} className="rounded-md border border-border bg-muted/30 px-2.5 py-1.5">
                <p className="text-xs font-medium text-foreground truncate">{doc.original_filename}</p>
                <p className="text-[11px] text-muted-foreground">
                  {doc.mime_type} · {(doc.size_bytes / 1024).toFixed(0)} КБ
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </dl>
  );
}

// ── Artifacts tab ─────────────────────────────────────────────────────────────

async function downloadArtifact(taskId: string, name: string): Promise<void> {
  const url = `/api/tasks/${taskId}/artifacts/${encodeURIComponent(name)}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    if (res.status === 401) {
      window.location.href = "/login";
    }
    return;
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
}

function ArtifactsTab({
  taskId,
  artifacts,
}: {
  taskId: string;
  artifacts: TaskResultResponse["artifacts"];
}) {
  if (artifacts.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">Артефактов нет</p>
    );
  }

  return (
    <ul className="space-y-2">
      {artifacts.map((a) => (
        <li
          key={a.name}
          className="rounded-md border border-border bg-card px-3 py-2.5 flex items-start justify-between gap-2"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground truncate">{a.name}</p>
            {a.description && (
              <p className="text-xs text-muted-foreground mt-0.5">{a.description}</p>
            )}
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {a.kind} · {a.mime_type ?? "—"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void downloadArtifact(taskId, a.name)}
            className="shrink-0 rounded-md border border-border bg-background px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            ↓
          </button>
        </li>
      ))}
    </ul>
  );
}

// ── JSON tab ──────────────────────────────────────────────────────────────────

function JsonTab({ data }: { data: Record<string, unknown> | null }) {
  if (!data) {
    return <p className="text-sm text-muted-foreground text-center py-8">Данных нет</p>;
  }
  const jsonStr = JSON.stringify(data, null, 2);
  return (
    <div className="relative">
      <div className="absolute top-0 right-0">
        <CopyButton getText={() => jsonStr} />
      </div>
      <pre className="text-[11px] font-mono text-foreground whitespace-pre-wrap break-all leading-relaxed pt-6">
        {jsonStr}
      </pre>
    </div>
  );
}

// ── Issues tab ────────────────────────────────────────────────────────────────

function IssuesTab({ issues }: { issues: ValidationIssueResponse[] }) {
  if (issues.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">Замечаний нет</p>
    );
  }
  return (
    <ul className="space-y-2">
      {issues.map((issue, i) => (
        <li key={i} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-xs font-semibold text-amber-800">
            {issue.field_name ? `${issue.field_name}: ` : ""}
            <span className="font-normal">{issue.message}</span>
          </p>
          {issue.raw_value !== undefined && issue.raw_value !== null && (
            <p className="text-[11px] text-amber-600 mt-0.5 font-mono">
              {String(issue.raw_value)}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
