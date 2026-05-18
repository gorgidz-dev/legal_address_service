/**
 * Админ-очередь модерации отзывов об адресах.
 *
 * Вкладки pending / published / rejected. Для pending — действия
 * «Опубликовать» / «Отклонить» (с опциональной причиной).
 */
import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { api, ApiError } from "../api";
import type { ModerationReview } from "../types";
import { StarRating } from "./StarRating";

type Tab = "pending" | "published" | "rejected";

const TAB_LABEL: Record<Tab, string> = {
  pending: "На модерации",
  published: "Опубликованы",
  rejected: "Отклонены",
};

export function AdminReviewModeration() {
  const [tab, setTab] = useState<Tab>("pending");
  const [items, setItems] = useState<ModerationReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .adminListReviews(tab)
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [tab]);

  async function moderate(review: ModerationReview, action: "publish" | "reject") {
    let note: string | undefined;
    if (action === "reject") {
      const input = window.prompt("Причина отклонения (необязательно):") ?? "";
      note = input.trim() || undefined;
    }
    setBusyId(review.id);
    setError(null);
    try {
      await api.adminModerateReview(review.id, action, note);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось применить действие");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="ds-modqueue">
      <div className="ds-modqueue__tabs">
        {(Object.keys(TAB_LABEL) as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`ds-chip${tab === t ? " ds-chip--active" : ""}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {error && <div className="ds-reviews__error">{error}</div>}

      {loading ? (
        <div className="ds-modqueue__empty">Загружаем…</div>
      ) : items.length === 0 ? (
        <div className="ds-modqueue__empty">
          {tab === "pending"
            ? "Очередь модерации пуста."
            : `Нет отзывов в статусе «${TAB_LABEL[tab].toLowerCase()}».`}
        </div>
      ) : (
        items.map((review) => (
          <article className="ds-modqueue__item" key={review.id}>
            <div className="ds-modqueue__head">
              <StarRating value={review.rating} size={14} />
              <span className="ds-modqueue__addr">{review.address_full}</span>
              <span className="ds-modqueue__email">· {review.client_email}</span>
              <time className="ds-reviews__date">
                {new Date(review.created_at).toLocaleDateString("ru-RU")}
              </time>
            </div>
            <p className="ds-modqueue__body">{review.body}</p>
            {review.moderation_note && (
              <p className="ds-reviews__error">Заметка: {review.moderation_note}</p>
            )}
            {tab === "pending" && (
              <div className="ds-modqueue__actions">
                <button
                  type="button"
                  className="ds-btn ds-btn--primary ds-btn--sm"
                  disabled={busyId === review.id}
                  onClick={() => moderate(review, "publish")}
                >
                  <Check size={14} /> Опубликовать
                </button>
                <button
                  type="button"
                  className="ds-btn ds-btn--ghost ds-btn--sm"
                  disabled={busyId === review.id}
                  onClick={() => moderate(review, "reject")}
                >
                  <X size={14} /> Отклонить
                </button>
              </div>
            )}
          </article>
        ))
      )}
    </section>
  );
}
