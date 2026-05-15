"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { TopUpBalanceResponse } from "@/lib/api/types";

const PRESETS = [10, 25, 50, 100];

export function TopUpForm() {
  const router = useRouter();
  const [amount, setAmount] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseFloat(amount);
    if (!parsed || parsed <= 0) {
      setError("Введите корректную сумму.");
      return;
    }

    setError(null);
    setSuccess(null);
    setIsSubmitting(true);

    try {
      const result = await clientFetch<TopUpBalanceResponse>("/balance/top-up", {
        method: "POST",
        body: { amount },
      });
      setSuccess(`Баланс пополнен. Новый баланс: ${result.balance_credits} кр.`);
      setAmount("");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Произошла ошибка. Попробуйте ещё раз.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      {/* Preset buttons */}
      <div className="grid grid-cols-4 gap-1.5">
        {PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => setAmount(String(preset))}
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            +{preset}
          </button>
        ))}
      </div>

      {/* Amount input */}
      <input
        type="number"
        step="0.01"
        min="0.01"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        disabled={isSubmitting}
        placeholder="Сумма"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      />

      {/* Feedback */}
      {error && (
        <p role="alert" className="text-sm text-destructive">{error}</p>
      )}
      {success && (
        <p role="status" className="text-sm text-green-700">{success}</p>
      )}

      <button
        type="submit"
        disabled={isSubmitting || !amount}
        className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSubmitting ? "Пополняется…" : "Пополнить"}
      </button>
    </form>
  );
}
