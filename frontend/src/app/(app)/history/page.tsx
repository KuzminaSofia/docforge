import type { Metadata } from "next";
import { serverFetch } from "@/lib/api/server";
import { HistoryTabs } from "./HistoryTabs";
import type {
  TransactionsHistoryResponse,
  PredictionsHistoryResponse,
} from "@/lib/api/types";

export const metadata: Metadata = { title: "Операции · DocForge" };

interface SearchParams {
  tab?: string;
  limit?: string;
  offset?: string;
}

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  const tab = params.tab === "predictions" ? "predictions" : "transactions";
  const limit = Math.min(Math.max(parseInt(params.limit ?? "20", 10), 1), 100);
  const offset = Math.max(parseInt(params.offset ?? "0", 10), 0);

  const [transactions, predictions] = await Promise.all([
    tab === "transactions"
      ? serverFetch<TransactionsHistoryResponse>("/history/transactions", {
          params: { limit, offset },
        }).catch(() => null)
      : Promise.resolve(null),
    tab === "predictions"
      ? serverFetch<PredictionsHistoryResponse>("/history/predictions", {
          params: { limit, offset },
        }).catch(() => null)
      : Promise.resolve(null),
  ]);

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Операции</h1>
      </header>

      <div className="flex flex-col gap-4 p-6 flex-1 overflow-y-auto">
        <HistoryTabs
          activeTab={tab}
          limit={limit}
          offset={offset}
          transactions={transactions}
          predictions={predictions}
        />
      </div>
    </div>
  );
}
