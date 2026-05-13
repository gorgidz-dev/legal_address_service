/**
 * Чат «клиент–собственник» по адресу.
 *
 * - REST: история через `api.getChatMessages`, отправка через `api.postChatMessage`.
 * - WebSocket: подписка на новые сообщения; cookie session — same-origin, httponly,
 *   браузер сам приложит при handshake.
 * - Push-уведомления (email + offline-нотификация) делает backend.
 */
import { FormEvent, useEffect, useRef, useState } from "react";
import { Loader2, Send, X } from "lucide-react";
import type { AddressChat, AddressChatMessage, CurrentUser } from "./types";
import { api } from "./api";

type Props = {
  chat: AddressChat;
  currentUser: CurrentUser;
  onClose: () => void;
};

function wsUrlForChat(chatId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/v1/ws/chats/${chatId}`;
}

export function AddressChatPanel({ chat, currentUser, onClose }: Props) {
  const [messages, setMessages] = useState<AddressChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsState, setWsState] = useState<"connecting" | "open" | "closed">("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .getChatMessages(chat.id)
      .then((items) => {
        if (alive) setMessages(items);
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

  async function send(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      const msg = await api.postChatMessage(chat.id, body);
      setMessages((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        return [...prev, msg];
      });
      setDraft("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  function authorName(message: AddressChatMessage): string {
    if (message.author_user_id === currentUser.id) return "Вы";
    if (message.author_user_id === chat.client_user_id) return chat.client_email;
    return chat.provider_name || "Собственник";
  }

  return (
    <div className="ds-chat-panel">
      <header className="ds-chat-panel__head">
        <div>
          <div className="ds-chat-panel__eyebrow">Чат с собственником</div>
          <strong>{chat.provider_name}</strong>
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

      <div className="ds-chat-panel__list">
        {loading ? (
          <div className="ds-chat-panel__loading">
            <Loader2 size={18} className="spin" /> загружаем историю…
          </div>
        ) : messages.length === 0 ? (
          <div className="ds-chat-panel__empty">
            Напишите первое сообщение — собственник получит уведомление на почту.
          </div>
        ) : (
          messages.map((m) => {
            const own = m.author_user_id === currentUser.id;
            return (
              <div
                key={m.id}
                className={`ds-chat-msg${own ? " ds-chat-msg--own" : ""}`}
              >
                <div className="ds-chat-msg__author">{authorName(m)}</div>
                <div className="ds-chat-msg__body">{m.body}</div>
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

      <form className="ds-chat-panel__compose" onSubmit={send}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Сообщение собственнику…"
          rows={2}
          maxLength={2000}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              send(e as unknown as FormEvent);
            }
          }}
        />
        <button
          type="submit"
          className="ds-btn ds-btn--primary ds-btn--sm"
          disabled={sending || draft.trim().length === 0}
        >
          {sending ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
          Отправить
        </button>
      </form>
    </div>
  );
}
