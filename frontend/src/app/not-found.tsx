import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background text-center p-8">
      <p className="text-6xl font-bold text-muted-foreground/30">404</p>
      <div>
        <h1 className="text-lg font-semibold text-foreground">Страница не найдена</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Страница не существует или была удалена.
        </p>
      </div>
      <Link
        href="/dashboard"
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        На главную
      </Link>
    </div>
  );
}
