"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/format";
import type { MLModelResponse, PredictAcceptedResponse } from "@/lib/api/types";

const ACCEPTED_TYPES: Record<string, string> = {
  "application/pdf": "PDF",
  "image/png": "PNG",
  "image/jpeg": "JPEG",
};

interface PredictFormProps {
  models: MLModelResponse[];
  userBalance: string;
  maxFileMb: number;
}

export function PredictForm({ models, userBalance, maxFileMb }: PredictFormProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  const [modelName, setModelName] = useState(models[0]?.name ?? "");
  const [targetSchema, setTargetSchema] = useState("");
  const [callbackUrl, setCallbackUrl] = useState("");

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const selectedModel = models.find((m) => m.name === modelName);
  const modelCost = parseFloat(selectedModel?.prediction_cost ?? "0");
  const balance = parseFloat(userBalance);
  const hasEnoughBalance = balance >= modelCost;

  // --- Валидация и выбор файла ---

  const pickFile = useCallback(
    (incoming: File) => {
      if (!ACCEPTED_TYPES[incoming.type]) {
        setFileError(`Формат не поддерживается (разрешены PDF, PNG, JPEG)`);
        return;
      }
      if (incoming.size > maxFileMb * 1024 * 1024) {
        setFileError(`Файл превышает ${maxFileMb} МБ`);
        return;
      }
      setFileError(null);
      setFile(incoming);
    },
    [maxFileMb],
  );

  const removeFile = () => {
    setFile(null);
    setFileError(null);
  };

  // --- Drag & Drop ---

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) pickFile(dropped);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) pickFile(selected);
    e.target.value = "";
  };

  // --- Отправка ---

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!file) {
      setSubmitError("Добавьте документ для обработки.");
      return;
    }
    if (!targetSchema.trim()) {
      setSubmitError("Укажите схему извлечения.");
      return;
    }

    setSubmitError(null);
    setIsSubmitting(true);

    const formData = new FormData();
    formData.append("document", file);
    formData.append("model_name", modelName);
    formData.append("target_schema", targetSchema.trim());
    if (callbackUrl.trim()) formData.append("callback_url", callbackUrl.trim());

    try {
      const result = await clientFetch<PredictAcceptedResponse>("/predict", {
        method: "POST",
        body: formData,
      });
      router.push(`/tasks/${result.task_id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Произошла ошибка. Попробуйте ещё раз.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const canSubmit =
    file !== null &&
    !!targetSchema.trim() &&
    models.length > 0 &&
    !!selectedModel &&
    hasEnoughBalance &&
    !isSubmitting;

  return (
    <form onSubmit={handleSubmit} className="flex flex-1 overflow-hidden">
      {/* ── Левая панель: загрузка ── */}
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
        {/* Дроп-зона */}
        {file ? (
          <div className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">{file.name}</p>
              <p className="text-xs text-muted-foreground">
                {ACCEPTED_TYPES[file.type]} · {formatBytes(file.size)}
              </p>
            </div>
            <button
              type="button"
              onClick={removeFile}
              className="ml-3 shrink-0 text-xs text-muted-foreground hover:text-destructive"
              aria-label={`Удалить ${file.name}`}
            >
              ✕
            </button>
          </div>
        ) : (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-10 text-center transition-colors",
              isDragging
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-muted/30",
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              className="sr-only"
              onChange={handleFileInput}
            />
            <span className="text-3xl">⇩</span>
            <p className="text-sm font-medium text-foreground">
              Перетащите документ сюда
            </p>
            <p className="text-xs text-muted-foreground">
              или{" "}
              <span className="text-primary underline">выберите файл</span>
            </p>
          </div>
        )}

        {/* Ошибка файла */}
        {fileError && (
          <div role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {fileError}
          </div>
        )}

        {/* Поддерживаемые форматы */}
        <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm">
          <p className="mb-2 font-medium text-foreground">Поддерживаемые форматы</p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt className="text-muted-foreground">Документы</dt>
            <dd className="text-foreground">PDF</dd>
            <dt className="text-muted-foreground">Изображения</dt>
            <dd className="text-foreground">PNG, JPEG</dd>
            <dt className="text-muted-foreground">Максимум</dt>
            <dd className="text-foreground">{maxFileMb} МБ</dd>
            <dt className="text-muted-foreground">Результат</dt>
            <dd className="text-foreground">Markdown, JSON, TXT</dd>
          </dl>
        </div>
      </div>

      {/* ── Правая панель: настройки ── */}
      <aside className="flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-border bg-card p-6">
        {/* Модель */}
        <div>
          <label htmlFor="model-select" className="mb-1.5 block text-sm font-medium text-foreground">
            Модель обработки
          </label>
          {models.length === 0 ? (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Активные модели не найдены
            </p>
          ) : (
            <select
              id="model-select"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              disabled={isSubmitting}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {models.map((m) => (
                <option key={m.id} value={m.name}>
                  {m.name} — {m.prediction_cost} кр.
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Схема извлечения */}
        <div>
          <label htmlFor="target-schema" className="mb-1.5 block text-sm font-medium text-foreground">
            Схема извлечения
          </label>
          <input
            id="target-schema"
            type="text"
            required
            value={targetSchema}
            onChange={(e) => setTargetSchema(e.target.value)}
            disabled={isSubmitting}
            placeholder="technical_passport"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
        </div>

        {/* Callback URL (опционально) */}
        <div>
          <label htmlFor="callback-url" className="mb-1.5 block text-sm font-medium text-foreground">
            Callback URL{" "}
            <span className="font-normal text-muted-foreground">(необязательно)</span>
          </label>
          <input
            id="callback-url"
            type="url"
            value={callbackUrl}
            onChange={(e) => setCallbackUrl(e.target.value)}
            disabled={isSubmitting}
            placeholder="https://example.com/webhook"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
        </div>

        {/* Информация о выбранной модели */}
        {selectedModel && (
          <div className="rounded-lg border border-border bg-muted/30 p-4 text-xs">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Выбранная модель
            </p>
            <p className="font-semibold text-foreground">{selectedModel.name}</p>
            <p className="mt-1 text-muted-foreground">{selectedModel.description}</p>
            <dl className="mt-2 space-y-1">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Backend</dt>
                <dd className="font-medium text-foreground">{selectedModel.backend_name}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Тип</dt>
                <dd className="font-medium text-foreground">{selectedModel.model_kind}</dd>
              </div>
            </dl>
          </div>
        )}

        {/* Проверка баланса */}
        <div
          className={cn(
            "rounded-lg border px-4 py-3 text-xs",
            hasEnoughBalance
              ? "border-green-200 bg-green-50 text-green-800"
              : "border-destructive/30 bg-destructive/10 text-destructive",
          )}
        >
          <p className="font-medium">
            {hasEnoughBalance ? "Баланс достаточен" : "Недостаточно кредитов"}
          </p>
          <div className="mt-1 flex justify-between">
            <span>Ваш баланс</span>
            <span className="font-medium">{userBalance} кр.</span>
          </div>
          <div className="flex justify-between">
            <span>Стоимость</span>
            <span className="font-medium">{selectedModel?.prediction_cost ?? "—"} кр.</span>
          </div>
        </div>

        {/* Ошибка отправки */}
        {submitError && (
          <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {submitError}
          </div>
        )}

        {/* Кнопка */}
        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Отправляется…" : "Запустить обработку"}
        </button>
      </aside>
    </form>
  );
}
