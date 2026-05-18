/**
 * Звёздный рейтинг — два режима:
 *  - display: только показ (дробное среднее, половинки через clip).
 *  - input:   кликабельный выбор 1-5 (для формы отзыва).
 */
import { Star } from "lucide-react";

type DisplayProps = {
  mode?: "display";
  value: number | null;
  count?: number;
  size?: number;
};

type InputProps = {
  mode: "input";
  value: number;
  onChange: (rating: number) => void;
  size?: number;
};

export function StarRating(props: DisplayProps | InputProps) {
  const size = props.size ?? 14;

  if (props.mode === "input") {
    return (
      <div className="ds-stars ds-stars--input" role="radiogroup" aria-label="Оценка">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={props.value === n}
            aria-label={`${n} из 5`}
            className={`ds-stars__btn${n <= props.value ? " ds-stars__btn--on" : ""}`}
            onClick={() => props.onChange(n)}
          >
            <Star size={size + 6} strokeWidth={1.6} />
          </button>
        ))}
      </div>
    );
  }

  const value = props.value ?? 0;
  return (
    <span className="ds-stars" aria-label={value ? `Рейтинг ${value} из 5` : "Нет оценок"}>
      {[1, 2, 3, 4, 5].map((n) => {
        // Доля заполнения этой звезды (0..1) — для дробного среднего.
        const fill = Math.max(0, Math.min(1, value - (n - 1)));
        return (
          <span key={n} className="ds-stars__star" style={{ width: size, height: size }}>
            <Star size={size} strokeWidth={1.6} className="ds-stars__bg" />
            <span className="ds-stars__fg" style={{ width: `${fill * 100}%` }}>
              <Star size={size} strokeWidth={1.6} />
            </span>
          </span>
        );
      })}
      {props.count !== undefined && (
        <span className="ds-stars__count">
          {value ? value.toFixed(1) : "—"}
          {props.count > 0 && ` · ${props.count}`}
        </span>
      )}
    </span>
  );
}
