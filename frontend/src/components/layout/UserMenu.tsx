"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { logoutAction } from "@/lib/actions/auth";
import { cn } from "@/lib/utils";
import type { UserResponse } from "@/lib/api/types";

interface UserMenuProps {
  user: UserResponse;
}

export function UserMenu({ user }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", handleClick);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative border-t border-border p-3">
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          {user.email[0].toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{user.email}</p>
          <p className="text-xs text-muted-foreground">{user.balance_credits} кр.</p>
        </div>
        <svg
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-3 right-3 mb-1 overflow-hidden rounded-lg border border-border bg-card shadow-lg"
        >
          <div className="border-b border-border px-3 py-2.5">
            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
            <p className="mt-0.5 text-sm font-semibold text-foreground">
              {user.balance_credits} <span className="text-xs font-normal text-muted-foreground">кр.</span>
            </p>
          </div>

          <div className="p-1">
            <Link
              href="/balance"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-accent"
            >
              <span className="text-base">＋</span>
              Пополнить баланс
            </Link>

            <form action={logoutAction}>
              <button
                type="submit"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
              >
                <span className="text-base">↩</span>
                Выйти
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
