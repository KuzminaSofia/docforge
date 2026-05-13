import Link from "next/link";
import { NavLink } from "./NavLink";
import { UserMenu } from "./UserMenu";
import type { UserResponse } from "@/lib/api/types";

const NAV_SECTIONS = [
  {
    title: "Рабочая область",
    links: [
      { href: "/dashboard", label: "Кабинет" },
      { href: "/predict", label: "Новая обработка" },
      { href: "/tasks", label: "Документы" },
    ],
  },
  {
    title: "Сервис",
    links: [
      { href: "/history", label: "Операции" },
    ],
  },
];

interface SidebarProps {
  user: UserResponse;
}

export function Sidebar({ user }: SidebarProps) {
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-border bg-card">
      <div className="p-4">
        <Link href="/dashboard" className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-primary text-xs font-bold text-primary-foreground">
            DF
          </span>
          <span className="text-sm font-semibold text-foreground">DocForge</span>
        </Link>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60 select-none">
              {section.title}
            </p>
            <div className="space-y-0.5">
              {section.links.map((link) => (
                <NavLink key={link.href} href={link.href}>
                  {link.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <UserMenu user={user} />
    </aside>
  );
}
