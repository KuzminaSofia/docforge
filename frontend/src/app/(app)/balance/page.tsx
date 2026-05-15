import Link from "next/link";
import type { Metadata } from "next";
import { getRequiredUser } from "@/lib/auth";
import { TopUpForm } from "./TopUpForm";

export const metadata: Metadata = { title: "Баланс · DocForge" };

export default async function BalancePage() {
  const user = await getRequiredUser();

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Баланс</h1>
        <Link
          href="/dashboard"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          ← Кабинет
        </Link>
      </header>

      <div className="flex flex-col gap-6 p-6 max-w-2xl">
        <p className="text-sm text-muted-foreground">
          Кредиты используются для запуска обработки документов.
          На текущем этапе пополнение реализовано как учебный сценарий без эквайринга.
        </p>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Current balance */}
          <div className="rounded-xl border border-border bg-card p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Текущий баланс
            </p>
            <p className="mt-3 text-4xl font-bold text-foreground">
              {user.balance_credits}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">кредитов</p>
          </div>

          {/* Top-up form */}
          <div className="rounded-xl border border-border bg-card p-6">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-4">
              Пополнить баланс
            </p>
            <TopUpForm />
          </div>
        </div>
      </div>
    </div>
  );
}
