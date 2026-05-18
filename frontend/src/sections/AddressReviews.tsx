/**
 * Блок отзывов на детальной карточке адреса.
 *
 * - Список опубликованных отзывов (+ ответ собственника).
 * - Свой отзыв клиента (любой статус) — со статус-бейджем, кнопками
 *   «Редактировать» / «Удалить». Редактирование возвращает отзыв на модерацию.
 * - Форма создания — если своего отзыва ещё нет и canReview=true.
 *
 * Бэк гейтит verified-purchase (нужна завершённая заявка) — фронт показывает
 * 403-ошибку текстом.
 */
import { useEffect, useState } from "react";
import { MessageSquare, Pencil, Trash2 } from "lucide-react";
import { api, ApiError } from "../api";
import type { MyReview, PublicReview } from "../types";
import { StarRating } from "./StarRating";

type Props = {
  addressId: string;
  /** Клиент ли текущий пользователь (может оставлять/редактировать отзыв). */
  canReview: boolean;
};

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: "На модерации", cls: "ds-rev-badge--pending" },
  published: { text: "Опубликован", cls: "ds-rev-badge--published" },
  rejected: { text: "Отклонён", cls: "ds-rev-badge--rejected" },
};

export function AddressReviews({ addressId, canReview }: Props) {
  const [reviews, setReviews] = useState<PublicReview[]>([]);
  const [myReview, setMyReview] = useState<MyReview | null>(null);
  const [loading, setLoading] = useState(true);

  // Форма (создание / редактирование).
  const [formOpen, setFormOpen] = useState(false);
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    const tasks: Promise<unknown>[] = [
      api
        .listAddressReviews(addressId)
        .then((r) => setReviews(r))
        .catch(() => setReviews([])),
    ];
    if (canReview) {
      tasks.push(
        api
          .getMyReview(addressId)
          .then((r) => setMyReview(r))
          .catch(() => setMyReview(null)),
      );
    }
    Promise.all(tasks).finally(() => setLoading(false));
  }

  useEffect(reload, [addressId, canReview]);

  function openCreate() {
    setRating(0);
    setBody("");
    setError(null);
    setFormOpen(true);
  }

  function openEdit(r: MyReview) {
    setRating(r.rating);
    setBody(r.body);
    setError(null);
    setFormOpen(true);
  }

  async function submit() {
    setError(null);
    if (rating < 1) {
      setError("Поставьте оценку от 1 до 5 звёзд.");
      return;
    }
    if (body.trim().length < 10) {
      setError("Отзыв слишком короткий — минимум 10 символов.");
      return;
    }
    setBusy(true);
    try {
      if (myReview) {
        const updated = await api.updateMyReview(myReview.id, {
          rating,
          body: body.trim(),
        });
        setMyReview(updated);
      } else {
        await api.createAddressReview(addressId, { rating, body: body.trim() });
      }
      setFormOpen(false);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось сохранить отзыв.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!myReview) return;
    if (!window.confirm("Удалить ваш отзыв?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteMyReview(myReview.id);
      setMyReview(null);
      setFormOpen(false);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось удалить отзыв.");
    } finally {
      setBusy(false);
    }
  }

  const badge = myReview ? STATUS_LABEL[myReview.status] : null;
  // Свой отзыв показываем в блоке «Ваш отзыв» — из общей ленты убираем,
  // чтобы не дублировался.
  const otherReviews = myReview
    ? reviews.filter((r) => r.id !== myReview.id)
    : reviews;

  return (
    <section className="ds-reviews">
      <h3 className="ds-reviews__title">
        <MessageSquare size={16} /> Отзывы
        {reviews.length > 0 && <span className="ds-reviews__n">{reviews.length}</span>}
      </h3>

      {/* Свой отзыв клиента */}
      {canReview && myReview && !formOpen && (
        <div className="ds-reviews__mine">
          <div className="ds-reviews__mine-head">
            <StarRating value={myReview.rating} size={13} />
            {badge && <span className={`ds-rev-badge ${badge.cls}`}>{badge.text}</span>}
            <span className="ds-reviews__mine-tag">Ваш отзыв</span>
          </div>
          <p className="ds-reviews__body">{myReview.body}</p>
          {myReview.status === "rejected" && myReview.moderation_note && (
            <p className="ds-reviews__error">
              Причина отклонения: {myReview.moderation_note}
            </p>
          )}
          {myReview.status === "pending" && (
            <p className="ds-reviews__hint">
              Отзыв ждёт проверки модератором и появится в каталоге после одобрения.
            </p>
          )}
          <div className="ds-reviews__mine-actions">
            <button
              type="button"
              className="ds-btn ds-btn--ghost ds-btn--sm"
              onClick={() => openEdit(myReview)}
              disabled={busy}
            >
              <Pencil size={13} /> Редактировать
            </button>
            <button
              type="button"
              className="ds-btn ds-btn--ghost ds-btn--sm"
              onClick={remove}
              disabled={busy}
            >
              <Trash2 size={13} /> Удалить
            </button>
          </div>
        </div>
      )}

      {/* Кнопка «оставить отзыв» — если своего ещё нет */}
      {canReview && !myReview && !formOpen && (
        <button
          type="button"
          className="ds-btn ds-btn--primary ds-btn--md"
          onClick={openCreate}
        >
          Оставить отзыв
        </button>
      )}

      {/* Форма создания / редактирования */}
      {canReview && formOpen && (
        <div className="ds-reviews__form">
          <div className="ds-reviews__form-row">
            <span className="ds-reviews__form-label">Ваша оценка</span>
            <StarRating mode="input" value={rating} onChange={setRating} />
          </div>
          <textarea
            className="ds-reviews__textarea"
            placeholder="Расскажите, как прошла сделка: подбор, документы, общение с собственником…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            maxLength={2000}
          />
          {error && <div className="ds-reviews__error">{error}</div>}
          <div className="ds-reviews__form-actions">
            <button
              type="button"
              className="ds-btn ds-btn--primary ds-btn--md"
              onClick={submit}
              disabled={busy}
            >
              {busy
                ? "Сохраняем…"
                : myReview
                  ? "Сохранить и отправить на модерацию"
                  : "Оставить отзыв"}
            </button>
            <button
              type="button"
              className="ds-btn ds-btn--ghost ds-btn--md"
              onClick={() => setFormOpen(false)}
              disabled={busy}
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {error && !formOpen && <div className="ds-reviews__error">{error}</div>}

      {/* Публичный список (без своего отзыва — он выше) */}
      {loading ? (
        <div className="ds-reviews__empty">Загружаем отзывы…</div>
      ) : otherReviews.length === 0 ? (
        <div className="ds-reviews__empty">
          {myReview
            ? "Других отзывов пока нет."
            : canReview
              ? "Пока нет отзывов. Будьте первым."
              : "Пока нет отзывов. Отзывы оставляют клиенты после завершённой сделки."}
        </div>
      ) : (
        <ul className="ds-reviews__list">
          {otherReviews.map((r) => (
            <li key={r.id} className="ds-reviews__item">
              <div className="ds-reviews__item-head">
                <StarRating value={r.rating} size={13} />
                <span className="ds-reviews__author">{r.author_name}</span>
                <time className="ds-reviews__date">
                  {new Date(r.created_at).toLocaleDateString("ru-RU")}
                </time>
              </div>
              <p className="ds-reviews__body">{r.body}</p>
              {r.owner_reply && (
                <div className="ds-reviews__reply">
                  <span className="ds-reviews__reply-label">Ответ собственника</span>
                  <p>{r.owner_reply}</p>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
