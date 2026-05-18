/**
 * Блок отзывов на детальной карточке адреса.
 *
 * - Список опубликованных отзывов (+ ответ собственника, если есть).
 * - Форма создания отзыва — показывается только когда canReview=true
 *   (клиент с завершённой заявкой; решение принимает родитель).
 * - Новый отзыв уходит на модерацию: после отправки показываем уведомление,
 *   в публичный список он не попадает до approve админом.
 */
import { useEffect, useState } from "react";
import { MessageSquare, ShieldCheck } from "lucide-react";
import { api, ApiError } from "../api";
import type { PublicReview } from "../types";
import { StarRating } from "./StarRating";

type Props = {
  addressId: string;
  /** Может ли текущий пользователь оставить отзыв (клиент с completed-заявкой). */
  canReview: boolean;
};

export function AddressReviews({ addressId, canReview }: Props) {
  const [reviews, setReviews] = useState<PublicReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .listAddressReviews(addressId)
      .then((r) => {
        if (alive) setReviews(r);
      })
      .catch(() => {
        if (alive) setReviews([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [addressId]);

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
      await api.createAddressReview(addressId, { rating, body: body.trim() });
      setSubmitted(true);
      setBody("");
      setRating(0);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось отправить отзыв.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ds-reviews">
      <h3 className="ds-reviews__title">
        <MessageSquare size={16} /> Отзывы
        {reviews.length > 0 && <span className="ds-reviews__n">{reviews.length}</span>}
      </h3>

      {/* Форма */}
      {canReview && !submitted && (
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
          <button
            type="button"
            className="ds-btn ds-btn--primary ds-btn--md"
            onClick={submit}
            disabled={busy}
          >
            {busy ? "Отправляем…" : "Оставить отзыв"}
          </button>
        </div>
      )}

      {canReview && submitted && (
        <div className="ds-reviews__sent">
          <ShieldCheck size={16} />
          Спасибо! Отзыв отправлен на модерацию и появится после проверки.
        </div>
      )}

      {/* Список */}
      {loading ? (
        <div className="ds-reviews__empty">Загружаем отзывы…</div>
      ) : reviews.length === 0 ? (
        <div className="ds-reviews__empty">
          Пока нет отзывов. {canReview ? "Будьте первым." : "Отзывы оставляют клиенты после завершённой сделки."}
        </div>
      ) : (
        <ul className="ds-reviews__list">
          {reviews.map((r) => (
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
