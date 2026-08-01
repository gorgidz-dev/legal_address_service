/**
 * Переписка по адресу: клиент, собственник и площадка в одной ветке.
 *
 * - REST: история через `api.getChatMessages`, отправка текстом или multipart.
 * - WebSocket: подписка на новые сообщения; cookie session — same-origin,
 *   httponly, браузер сам приложит при handshake.
 * - Уведомления офлайн-участникам (in-app, почта, push) делает backend.
 *
 * Подпись автора приходит с сервера (`author_name`), а не собирается здесь.
 * Раньше панель считала «всё, что не клиент» собственником — и сообщение
 * площадки подписывалось названием организации собственника.
 */
import { FormEvent, useEffect, useRef, useState } from "react";
import { Loader2, Paperclip, Send, X } from "lucide-react";
import type { AddressChat, AddressChatMessage, ChatAuthorSide, CurrentUser } from "./types";
import { api, apiDownloadUrl } from "./api";
import { DownloadLink } from "./DownloadLink";
import { formatFileSize } from "./fileSize";

type Props = {
  chat: AddressChat;
  currentUser: CurrentUser;
  onClose: () => void;
  /** Ветка прочитана — родитель гасит счётчик непрочитанного. */
  onRead?: (chatId: string) => void;
};

/** Должно совпадать с MAX_ATTACHMENTS_PER_MESSAGE на сервере. */
const MAX_FILES = 5;
/** Должно совпадать с MAX_ATTACHMENT_BYTES на сервере. */
const MAX_FILE_BYTES = 15 * 1024 * 1024;

const SIDE_LABELS: Record<ChatAuthorSide, string> = {
  client: "Клиент",
  owner: "Собственник",
  staff: "Площадка"
};

function wsUrlForChat(chatId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/v1/ws/chats/${chatId}`;
}

export function AddressChatPanel({ chat, currentUser, onClose, onRead }: Props) {
  const [messages, setMessages] = useState<AddressChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsState, setWsState] = useState<"connecting" | "open" | "closed">("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .getChatMessages(chat.id)
      .then((items) => {
        if (!alive) return;
        setMessages(items);
        // Отметку ставим после того, как история действительно показана:
        // погасить счётчик у ветки, которая не открылась, значит потерять её.
        api
          .markChatRead(chat.id)
          .then(() => onRead?.(chat.id))
          .catch(() => {
            /* не критично: счётчик догорит при следующем открытии */
          });
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // onRead намеренно не в зависимостях: родитель пересоздаёт колбэк на
    // каждый рендер, и история перезапрашивалась бы бесконечно.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.id]);

  useEffect(() => {
    const ws = new WebSocket(wsUrlForChat(chat.id));
    wsRef.current = ws;
    setWsState("connecting");
    ws.onopen = () => setWsState("open");
    ws.onclose = () => setWsState("closed");
    ws.onerror = () => setWsState("closed");
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.type === "message" && parsed.payload) {
          setMessages((prev) => {
            if (prev.some((m) => m.id === parsed.payload.id)) return prev;
            return [...prev, parsed.payload as AddressChatMessage];
          });
        }
      } catch {
        // ignore
      }
    };
    return () => {
      ws.close();
    };
  }, [chat.id]);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  function addFiles(incoming: FileList | null) {
    if (!incoming || incoming.length === 0) return;
    const picked = Array.from(incoming);
    const tooBig = picked.find((file) => file.size > MAX_FILE_BYTES);
    if (tooBig) {
      setError(`Файл «${tooBig.name}» больше ${MAX_FILE_BYTES / 1024 / 1024} МБ`);
      return;
    }
    setFiles((prev) => {
      const merged = [...prev, ...picked];
      if (merged.length > MAX_FILES) {
        setError(`За раз можно приложить не больше ${MAX_FILES} файлов`);
        return merged.slice(0, MAX_FILES);
      }
      setError(null);
      return merged;
    });
  }

  function dropFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if ((!body && files.length === 0) || sending) return;
    setSending(true);
    setError(null);
    try {
      let msg: AddressChatMessage;
      if (files.length > 0) {
        const form = new FormData();
        form.append("body", body);
        files.forEach((file) => form.append("files", file));
        msg = await api.postChatMessageWithFiles(chat.id, form);
      } else {
        msg = await api.postChatMessage(chat.id, body);
      }
      setMessages((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        return [...prev, msg];
      });
      setDraft("");
      setFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  const canSend = !sending && (draft.trim().length > 0 || files.length > 0);

  return (
    <div className="ds-chat-panel">
      <header className="ds-chat-panel__head">
        <div>
          <div className="ds-chat-panel__eyebrow">Переписка по адресу</div>
          <strong>{chat.provider_name || "Собственник"}</strong>
          <span className="ds-chat-panel__sub">{chat.address_full}</span>
        </div>
        <div className="ds-chat-panel__head-right">
          <span
            className={`ds-chat-panel__dot ds-chat-panel__dot--${wsState}`}
            title={
              wsState === "open"
                ? "Соединение установлено"
                : wsState === "connecting"
                  ? "Подключение…"
                  : "Соединение разорвано"
            }
          />
          <button type="button" className="text-action" onClick={onClose}>
            <X size={16} /> Закрыть
          </button>
        </div>
      </header>

      <div
        className="ds-chat-panel__list"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          addFiles(e.dataTransfer.files);
        }}
      >
        {loading ? (
          <div className="ds-chat-panel__loading">
            <Loader2 size={18} className="spin" /> загружаем историю…
          </div>
        ) : messages.length === 0 ? (
          <div className="ds-chat-panel__empty">
            Здесь переписка клиента, собственника и площадки. Можно приложить
            документы — они останутся в этой ветке.
          </div>
        ) : (
          messages.map((m) => {
            const own = m.author_user_id === currentUser.id;
            return (
              <div key={m.id} className={`ds-chat-msg${own ? " ds-chat-msg--own" : ""}`}>
                <div className="ds-chat-msg__author">
                  {own ? "Вы" : m.author_name}
                  {!own && (
                    <span className={`ds-chat-side ds-chat-side--${m.author_side}`}>
                      {SIDE_LABELS[m.author_side]}
                    </span>
                  )}
                </div>
                {m.body ? <div className="ds-chat-msg__body">{m.body}</div> : null}
                {m.attachments.length > 0 ? (
                  <div className="ds-chat-files">
                    {m.attachments.map((file) => (
                      <DownloadLink
                        className="ds-chat-file"
                        href={apiDownloadUrl(file.download_url)}
                        key={file.id}
                        title={file.original_filename}
                      >
                        <Paperclip size={14} />
                        <span className="ds-chat-file__name">{file.original_filename}</span>
                        <span className="ds-chat-file__size">
                          {formatFileSize(file.size_bytes)}
                        </span>
                      </DownloadLink>
                    ))}
                  </div>
                ) : null}
                <div className="ds-chat-msg__time">
                  {new Date(m.created_at).toLocaleString("ru-RU", {
                    day: "2-digit",
                    month: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit"
                  })}
                </div>
              </div>
            );
          })
        )}
        <div ref={listEndRef} />
      </div>

      {error && <div className="ds-chat-panel__error">{error}</div>}

      {files.length > 0 && (
        <ul className="ds-chat-drafts">
          {files.map((file, index) => (
            <li className="ds-chat-draft" key={`${file.name}-${index}`}>
              <Paperclip size={13} />
              <span className="ds-chat-draft__name">{file.name}</span>
              <span className="ds-chat-draft__size">{formatFileSize(file.size)}</span>
              <button
                type="button"
                aria-label={`Убрать ${file.name}`}
                className="ds-chat-draft__drop"
                onClick={() => dropFile(index)}
              >
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="ds-chat-panel__compose" onSubmit={send}>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => addFiles(e.target.files)}
        />
        <button
          type="button"
          className="ds-chat-attach"
          title="Приложить документ"
          aria-label="Приложить документ"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={16} />
        </button>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Сообщение — его увидят собственник и площадка…"
          rows={2}
          maxLength={2000}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              send(e as unknown as FormEvent);
            }
          }}
        />
        <button type="submit" className="ds-btn ds-btn--primary ds-btn--sm" disabled={!canSend}>
          {sending ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
          Отправить
        </button>
      </form>
    </div>
  );
}
