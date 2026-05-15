import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { serverFetch } from "@/lib/api/server";
import { NotFoundError } from "@/lib/api/errors";
import { TaskDetailClient } from "./TaskDetailClient";
import type { TaskResultResponse } from "@/lib/api/types";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return { title: `Задача ${id.slice(0, 8)}… · DocForge` };
}

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const initial = await serverFetch<TaskResultResponse>(`/tasks/${id}/result`).catch((err) => {
    if (err instanceof NotFoundError) notFound();
    return null;
  });

  if (!initial) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Не удалось загрузить задачу</p>
      </div>
    );
  }

  return <TaskDetailClient taskId={id} initial={initial} />;
}
