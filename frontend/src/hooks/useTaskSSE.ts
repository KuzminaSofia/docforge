"use client";

import { useEffect, useRef } from "react";
import type { TaskStatusResponse } from "@/lib/api/types";

type Callbacks = {
  onStatus: (data: TaskStatusResponse) => void;
  onDone: (data: TaskStatusResponse) => void;
  onError?: () => void;
};

/**
 * Подписывается на SSE-поток статуса задачи GET /api/tasks/{taskId}/stream.
 * Вызывает onStatus при каждом промежуточном событии,
 * onDone при терминальном статусе (стрим закрывается автоматически).
 * При enabled=false соединение не открывается.
 */
export function useTaskSSE(taskId: string, enabled: boolean, callbacks: Callbacks): void {
  const cbRef = useRef(callbacks);
  cbRef.current = callbacks;

  useEffect(() => {
    if (!enabled) return;

    const es = new EventSource(`/api/tasks/${taskId}/stream`, { withCredentials: true });

    es.addEventListener("status", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as TaskStatusResponse;
        cbRef.current.onStatus(data);
      } catch {}
    });

    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as TaskStatusResponse;
        cbRef.current.onDone(data);
      } catch {}
      es.close();
    });

    es.addEventListener("stream_error", () => {
      cbRef.current.onError?.();
      es.close();
    });

    es.onerror = () => {
      cbRef.current.onError?.();
      es.close();
    };

    return () => es.close();
  }, [taskId, enabled]);
}
