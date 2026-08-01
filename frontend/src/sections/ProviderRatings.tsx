/**
 * Внутренняя оценка работы собственников — экран оператора.
 *
 * Это не рейтинг адреса: тот ставят клиенты и он публичный. Здесь оценка
 * того, как собственник работает с площадкой, и она не показывается никому,
 * кроме оператора.
 *
 * Метрика без данных подписана «нет данных», а не нулём: собственник, которому
 * ещё не писали, отвечает не плохо — про него просто ничего не известно.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import type { ProviderRating, RatingMetric } from "../types";
import { ListEmpty, ListError, ListLoading } from "../ui/ListState";

function scoreTone(score: number | null): string {
  if (score === null) return "prating__score prating__score--unknown";
  if (score >= 75) return "prating__score prating__score--good";
  if (score >= 50) return "prating__score prating__score--mid";
  return "prating__score prating__score--bad";
}

function hoursText(metric: RatingMetric): string {
  if (metric.value === null) return "нет данных";
  const hours = metric.value;
  if (hours < 1) return `${Math.round(hours * 60)} мин`;
  if (hours < 24) return `${hours.toFixed(1)} ч`;
  return `${(hours / 24).toFixed(1)} сут`;
}

function percentText(metric: RatingMetric): string {
  if (metric.value === null) return "нет данных";
  return `${Math.round(metric.value * 100)}%`;
}

export function ProviderRatings() {
  const [rows, setRows] = useState<ProviderRating[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setError(null);
    api
      .providerRatings()
      .then(setRows)
      .catch((err) => setError((err as Error).message));
  }

  useEffect(reload, []);

  if (error) return <ListError message={error} onRetry={reload} />;
  if (rows === null) return <ListLoading rows={3} />;
  if (rows.length === 0) {
    return <ListEmpty title="Оценивать пока некого" text="Нет ни одного собственника с данными." />;
  }

  return (
    <div className="prating">
      <div className="timeline-title">
        <strong>Оценка работы собственников</strong>
      </div>
      <p className="prating__note">
        Внутренний показатель. Клиентам не показывается и в карточку адреса не попадает.
      </p>

      <div className="prating__list">
        {rows.map((row) => (
          <article className="prating__row" key={row.provider_id}>
            <div className="prating__head">
              <strong>{row.provider_name}</strong>
              <span className={scoreTone(row.score)}>
                {row.score === null ? "нет данных" : row.score}
              </span>
            </div>
            <dl className="prating__metrics">
              <div>
                <dt>Ответ в чате</dt>
                <dd>
                  {hoursText(row.response)}
                  {row.response.sample ? (
                    <small> · {row.response.sample} ответ(ов)</small>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>Заполненность карточек</dt>
                <dd>
                  {percentText(row.cards)}
                  {row.cards.sample ? <small> · {row.cards.sample} адрес(ов)</small> : null}
                </dd>
              </div>
              <div>
                <dt>Возвраты документов</dt>
                <dd>
                  {percentText(row.documents)}
                  {row.documents.sample ? (
                    <small> · {row.documents.sample} загрузк(и)</small>
                  ) : null}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
