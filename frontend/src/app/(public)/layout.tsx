export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            DF
          </span>
          <h1 className="mt-3 text-xl font-semibold text-foreground">DocForge</h1>
        </div>
        {children}
      </div>
    </div>
  );
}
