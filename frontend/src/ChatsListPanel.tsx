/**
 * Список чатов текущего пользователя.
 *
 * Backend `/api/v1/chats` сам решает что показывать:
 * - клиент видит свои чаты;
 * - собственник — все чаты по адресам своей организации;
 * - админ — все чаты.
 *
 * При клике на строку открывается `AddressChatPanel` в модалке поверх.
 */
import { useEffect, useState } from "react";
import { Loader2, MessageSquare, RefreshCw, X } from "lucide-react";
import { AddressChatPanel } from "./AddressChatPanel";
import { api } from "./api";
import type { AddressChat, CurrentUser } from "./types";

type Props = {
  currentUser: CurrentUser;
  /** Опционально — сколько последних чатов показать; null = всё. */
  limit?: number | null;
};

function formatTime(value: string | null): string {
  if (!value) return "—";
  const ts = Date.parse(value);
  if (!Number.isFinite(ts)) return value;
  return new Date(ts).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function ChatsListPanel({ currentUser, limit = null }: Props) {
  const [items, setItems] = useState<AddressChat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AddressChat | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .listMyChats()
      .then((rows) => {
        if (!alive) return;
        setItems(limit ? rows.slice(0, limit) : rows);
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
  }, [refreshKey, limit]);

  return (
    <section className="ds-chatlist">
      <header className="ds-chatlist__head">
        <span className="ds-chatlist__count">
          {loading ? "…" : `${items.length} ${items.length === 1 ? "чат" : "чатов"}`}
        </span>
        <button
          type="button"
          className="ds-btn ds-btn--ghost ds-btn--sm"
          onClick={() => setRefreshKey((k) => k + 1)}
          title="Обновить"
        >
          <RefreshCw size={14} /> Обновить
        </button>
      </header>

      {error && <div className="ds-input-error-text">{error}</div>}

      {loading ? (
        <div className="ds-chatlist__loading">
          <Loader2 size={16} className="spin" /> Загружаем…
        </div>
      ) : items.length === 0 ? (
        <div className="ds-chatlist__empty">
          <MessageSquare size={20} strokeWidth={1.6} />
          <span>
            {currentUser.role === "client"
              ? "Пока нет переписок с собственниками."
              : currentUser.role === "owner"
                ? "Пока нет входящих сообщений."
                : "Чаты ещё не созданы."}
          </span>
        </div>
      ) : (
        <ul className="ds-chatlist__rows">
          {items.map((chat) => (
            <li key={chat.id}>
              <button
                type="button"
                className="ds-chatlist__row"
                onClick={() => setSelected(chat)}
              >
                <div className="ds-chatlist__row-main">
                  <strong>{chat.address_full}</strong>
                  <span>
                    {currentUser.role === "client"
                      ? chat.provider_name
                      : chat.client_email}
                  </span>
                </div>
                <div className="ds-chatlist__row-meta">
                  {formatTime(chat.last_message_at || chat.created_at)}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div
            className="modal-panel"
            style={{ maxWidth: 640, width: "100%", padding: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            <AddressChatPanel
              chat={selected}
              currentUser={currentUser}
              onClose={() => setSelected(null)}
            />
          </div>
        </div>
      )}
    </section>
  );
}
