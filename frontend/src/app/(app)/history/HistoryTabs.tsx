"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { formatDateTime } from "@/lib/format";
import { TaskStatusBadge } from "@/components/tasks/TaskStatusBadge";
import { cn } from "@/lib/utils";
import type {
  TransactionsHistoryResponse,
  PredictionsHistoryResponse,
  TransactionHistoryItemResponse,
  PredictionHistoryItemResponse,
} from "@/lib/api/types";

type Tab = "transactions" | "predictions";

interface Props {
  activeTab: Tab;
  limit: number;
  offset: number;
  transactions: TransactionsHistoryResponse | null;
  predictions: PredictionsHistoryResponse | null;
}

function buildUrl(tab: Tab, limit: number, offset: number) {
  const p = new URLSearchParams({ tab, limit: String(limit), offset: String(offset) });
  return `/history?${p.toString()}`;
}

export function HistoryTabs({ activeTab, limit, offset, transactions, predictions }: Props) {
  const activeItems =
    activeTab === "transactions"
      ? (transactions?.items ?? [])
      : (predictions?.items ?? []);

  const hasError =
    activeTab === "transactions" ? !transactions : !predictions;

  const hasPrev = offset > 0;
  const hasNext = activeItems.length === limit;

  return (
    <div className="flex flex-col gap-4">
      {/* Tab bar */}
      <div className="flex border-b border-border">
        {(["transactions", "predictions"] as Tab[]).map((tab) => (
          <Link
            key={tab}
            href={buildUrl(tab, limit, 0)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium transition-colors relative",
              activeTab === tab
                ? "text-foreground after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab === "transactions" ? "Транзакции" : "Предсказания"}
          </Link>
        ))}

        <div className="ml-auto flex items-center pr-1">
          <LimitSelect limit={limit} activeTab={activeTab} />
        </div>
      </div>

      {/* Error */}
      {hasError && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-6 text-center">
          <p className="text-sm font-medium text-destructive">Не удалось загрузить данные</p>
          <p className="mt-1 text-xs text-muted-foreground">Обновите страницу или повторите позже</p>
        </div>
      )}

      {/* Empty */}
      {!hasError && activeItems.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card py-16 text-center">
          <p className="text-sm font-medium text-foreground">Записей пока нет</p>
        </div>
      )}

      {/* Table */}
      {activeItems.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {activeTab === "transactions" ? (
            <TransactionsTable items={transactions?.items ?? []} />
          ) : (
            <PredictionsTable items={predictions?.items ?? []} />
          )}
        </div>
      )}

      {/* Pagination */}
      {activeItems.length > 0 && (
        <div className="flex items-center justify-between">
          {hasPrev ? (
            <Link
              href={buildUrl(activeTab, limit, offset - limit)}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              ← Назад
            </Link>
          ) : (
            <span />
          )}
          {hasNext && (
            <Link
              href={buildUrl(activeTab, limit, offset + limit)}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              Вперёд →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

// ── Limit selector ────────────────────────────────────────────────────────────

function LimitSelect({ limit, activeTab }: { limit: number; activeTab: Tab }) {
  const router = useRouter();

  return (
    <select
      value={String(limit)}
      onChange={(e) =>
        router.push(buildUrl(activeTab, parseInt(e.target.value, 10), 0))
      }
      className="rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus-visible:outline-none"
    >
      {[10, 20, 50].map((n) => (
        <option key={n} value={String(n)}>
          {n} / стр.
        </option>
      ))}
    </select>
  );
}

// ── Transactions table ────────────────────────────────────────────────────────

function TransactionsTable({ items }: { items: TransactionHistoryItemResponse[] }) {
  return (
    <>
      <div className="grid grid-cols-[140px_minmax(0,1fr)_90px_110px] gap-x-4 border-b border-border bg-muted/40 px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <span>Дата</span>
        <span>Задача</span>
        <span>Тип</span>
        <span className="text-right">Сумма</span>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <li key={item.id} className="grid grid-cols-[140px_minmax(0,1fr)_90px_110px] items-center gap-x-4 px-4 py-3">
            <span className="text-xs text-muted-foreground">{formatDateTime(item.created_at)}</span>
            <span className="font-mono text-xs truncate">
              {item.task_id ? (
                <Link
                  href={`/tasks/${item.task_id}`}
                  className="text-primary/80 hover:text-primary transition-colors"
                >
                  {item.task_id}
                </Link>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </span>
            <span className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium w-fit",
              item.transaction_type === "credit"
                ? "bg-green-100 text-green-700"
                : "bg-red-100 text-red-700",
            )}>
              {item.transaction_type === "credit" ? "Пополнение" : "Списание"}
            </span>
            <span className={cn(
              "text-right text-sm font-semibold",
              item.transaction_type === "credit" ? "text-green-700" : "text-red-600",
            )}>
              {item.transaction_type === "credit" ? "+" : "−"}{item.amount} кр.
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

// ── Predictions table ─────────────────────────────────────────────────────────

function PredictionsTable({ items }: { items: PredictionHistoryItemResponse[] }) {
  return (
    <>
      <div className="grid grid-cols-[140px_minmax(0,1fr)_120px_72px] gap-x-4 border-b border-border bg-muted/40 px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <span>Дата</span>
        <span>Задача</span>
        <span>Статус</span>
        <span className="text-right">Кредиты</span>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              href={item.task_id ? `/tasks/${item.task_id}` : "#"}
              className="grid grid-cols-[140px_minmax(0,1fr)_120px_72px] items-center gap-x-4 px-4 py-3 transition-colors hover:bg-accent/50"
            >
              <span className="text-xs text-muted-foreground">{formatDateTime(item.created_at)}</span>
              {item.task_id ? (
                <span className="font-mono text-xs text-primary/80 truncate">{item.task_id}</span>
              ) : (
                <span className="font-mono text-xs text-muted-foreground">—</span>
              )}
              <TaskStatusBadge status={item.status} />
              <span className="text-right text-xs text-muted-foreground">{item.spent_credits}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
