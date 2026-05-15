"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
        <span className="text-xl text-destructive">!</span>
      </div>
      <div>
        <h2 className="text-lg font-semibold text-foreground">Что-то пошло не так</h2>
        <p className="mt-1 text-sm text-muted-foreground max-w-sm">
          Произошла непредвиденная ошибка. Попробуйте обновить страницу или вернуться на главную.
        </p>
      </div>
      <div className="flex gap-3">
        <button
          onClick={reset}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Попробовать снова
        </button>
        <Link
          href="/dashboard"
          className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          На главную
        </Link>
      </div>
    </div>
  );
}
