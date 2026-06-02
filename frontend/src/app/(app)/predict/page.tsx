import Link from "next/link";
import type { Metadata } from "next";
import { getRequiredUser } from "@/lib/auth";
import { serverFetch } from "@/lib/api/server";
import { PredictForm } from "./PredictForm";
import type { MLModelResponse } from "@/lib/api/types";

export const metadata: Metadata = { title: "Новая обработка · DocForge" };

export default async function PredictPage({
  searchParams,
}: {
  searchParams: Promise<{ model?: string; schema?: string }>;
}) {
  const [user, models, params] = await Promise.all([
    getRequiredUser(),
    serverFetch<MLModelResponse[]>("/predict/models").catch(() => [] as MLModelResponse[]),
    searchParams,
  ]);

  const maxFileMb = parseInt(process.env.MAX_FILE_MB ?? "50", 10);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Новая обработка документа</h1>
        <Link
          href="/tasks"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          ← Документы
        </Link>
      </header>

      <PredictForm
        models={models}
        userBalance={user.balance_credits}
        maxFileMb={maxFileMb}
        initialModelName={params.model}
        initialSchema={params.schema}
      />
    </div>
  );
}
