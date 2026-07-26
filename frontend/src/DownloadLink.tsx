/**
 * Ссылка на скачивание файла из API.
 *
 * Обычный `<a href>` уводил браузер из SPA: при протухшей сессии пользователь
 * оказывался на белой странице с JSON `{"error": ...}` и терял всё несохранённое
 * состояние, а вернуться мог только кнопкой «Назад». Здесь запрос идёт через
 * fetch с куками: 401 отдаём общему обработчику сессии (уведёт на вход), любую
 * другую ошибку показываем прямо в интерфейсе, а успешный ответ отдаём как blob.
 *
 * href остаётся настоящим — «Открыть в новой вкладке» и копирование ссылки
 * работают как раньше.
 */
import { Loader2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { SESSION_EXPIRED_EVENT } from "./api";

/** Имя файла из Content-Disposition; иначе — последний сегмент пути. */
function filenameFrom(response: Response, href: string): string {
  const disposition = response.headers.get("Content-Disposition") || "";
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      /* испорченный заголовок — падаем в следующий вариант */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  if (plain?.[1]) return plain[1];
  return decodeURIComponent(href.split("?")[0].split("/").pop() || "document");
}

export function DownloadLink({
  href,
  className,
  children,
  title
}: {
  href: string;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download(event: React.MouseEvent<HTMLAnchorElement>) {
    // Ctrl/Cmd/Shift-клик и средняя кнопка — пусть браузер делает своё.
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    try {
      const response = await fetch(href, { credentials: "include" });

      if (response.status === 401) {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
        setError("Сессия истекла — войдите заново.");
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setError(body?.error?.message || `Не удалось скачать (HTTP ${response.status})`);
        return;
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filenameFrom(response, href);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      // Отзываем на следующем тике: Safari успевает начать загрузку.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (err) {
      setError((err as Error).message || "Сеть недоступна");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <a className={className} href={href} onClick={download} title={title}>
        {busy ? <Loader2 className="spin" size={15} /> : null}
        {children}
      </a>
      {error ? <span className="download-link__error">{error}</span> : null}
    </>
  );
}
