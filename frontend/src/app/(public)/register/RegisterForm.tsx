"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { clientFetch } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { AuthResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function RegisterForm() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const passwordsMatch = !confirmPassword || password === confirmPassword;
  const canSubmit =
    !!email && password.length >= 8 && password === confirmPassword && !isLoading;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (password !== confirmPassword) {
      setError("Пароли не совпадают.");
      return;
    }

    setError(null);
    setIsLoading(true);

    const normalizedEmail = email.trim().toLowerCase();

    try {
      await clientFetch<AuthResponse>("/auth/register", {
        method: "POST",
        body: { email: normalizedEmail, password },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Произошла непредвиденная ошибка. Попробуйте ещё раз.");
      setIsLoading(false);
      return;
    }

    // Регистрация прошла успешно — выполняем автоматический вход.
    // /auth/register не устанавливает cookie, поэтому нужен отдельный запрос.
    try {
      await clientFetch<AuthResponse>("/auth/login", {
        method: "POST",
        body: { email: normalizedEmail, password },
      });
      router.push("/dashboard");
      router.refresh();
    } catch {
      // Аккаунт создан, но автологин не удался (например, сервер перегружен).
      // Направляем на страницу входа — пользователь сможет войти вручную.
      setError("Аккаунт успешно создан, но войти автоматически не удалось. Пожалуйста, войдите вручную.");
      setIsLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
      <h2 className="mb-1 text-lg font-semibold text-foreground">Регистрация</h2>
      <p className="mb-6 text-sm text-muted-foreground">
        Создайте аккаунт для доступа к ML-сервису.
      </p>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && (
          <div
            role="alert"
            className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        )}

        {/* Email */}
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-foreground">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isLoading}
            placeholder="you@example.com"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>

        {/* Пароль */}
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-foreground">
            Пароль
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              placeholder="Минимум 8 символов"
              className="w-full rounded-md border border-input bg-background px-3 py-2 pr-20 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground"
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showPassword ? "Скрыть" : "Показать"}
            </button>
          </div>
        </div>

        {/* Повторите пароль */}
        <div>
          <label
            htmlFor="confirm-password"
            className="mb-1.5 block text-sm font-medium text-foreground"
          >
            Повторите пароль
          </label>
          <div className="relative">
            <input
              id="confirm-password"
              type={showConfirm ? "text" : "password"}
              required
              minLength={8}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isLoading}
              placeholder="Повторите пароль"
              className={cn(
                "w-full rounded-md border bg-background px-3 py-2 pr-20 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                confirmPassword && !passwordsMatch ? "border-destructive" : "border-input",
              )}
            />
            <button
              type="button"
              onClick={() => setShowConfirm((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground"
              aria-label={showConfirm ? "Скрыть пароль" : "Показать пароль"}
            >
              {showConfirm ? "Скрыть" : "Показать"}
            </button>
          </div>

          {/* Hint о совпадении */}
          {confirmPassword && (
            <p
              className={cn(
                "mt-1.5 text-xs",
                passwordsMatch ? "text-green-600" : "text-destructive",
              )}
            >
              {passwordsMatch ? "Пароли совпадают" : "Пароли не совпадают"}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? "Создание аккаунта…" : "Зарегистрироваться"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Уже есть аккаунт?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Войти
        </Link>
      </p>
    </div>
  );
}
