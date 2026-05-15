import { Suspense } from "react";
import { LoginForm } from "./LoginForm";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
          <div className="h-6 w-40 animate-pulse rounded bg-muted" />
          <div className="mt-6 space-y-4">
            <div className="h-10 animate-pulse rounded bg-muted" />
            <div className="h-10 animate-pulse rounded bg-muted" />
            <div className="h-10 animate-pulse rounded bg-muted" />
          </div>
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
