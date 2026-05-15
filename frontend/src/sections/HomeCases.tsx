/**
 * Карточки кейсов / отзывов клиентов.
 *
 * MVP — статичные цитаты. Когда наберётся достаточно реальных,
 * заменим на CMS-фид (или таблицу `client_reviews` в БД).
 */
import { Quote } from "lucide-react";

type Case = {
  quote: string;
  author: string;
  role: string;
  /** Опционально — задача клиента. */
  context?: string;
};

const CASES: Case[] = [
  {
    quote:
      "Регистрировали ООО за неделю — нужен был быстрый и легальный юр-адрес. Подобрали Тверская за 2 часа, гарантийку выдали в тот же день. В ФНС зашли без вопросов.",
    author: "Алексей Морозов",
    role: "Учредитель, ИТ-стартап",
    context: "Первичная регистрация ООО",
  },
  {
    quote:
      "Меняли адрес давно работающей компании — налоговая по старому адресу резко изменила трактовку. Сервис выручил: и договор, и письмо, и сопровождение в одном пакете.",
    author: "Мария Зайцева",
    role: "Финдиректор",
    context: "Смена юр. адреса",
  },
  {
    quote:
      "Поначалу пугало, что собственник «виртуальный». Но в чате договорились о выезде на объект, посмотрели реальный офис. Всё чисто, теперь работаем второй год.",
    author: "Дмитрий Канарейкин",
    role: "Гендиректор, торговля",
    context: "Адрес с корреспонденцией",
  },
];

export function HomeCases() {
  return (
    <section className="ds-cases" aria-label="Кейсы клиентов">
      <header className="ds-cases__head">
        <span className="ds-cases__eyebrow">Кейсы клиентов</span>
        <h2 className="ds-cases__title">Кому уже помогли</h2>
      </header>
      <div className="ds-cases__grid">
        {CASES.map((c, i) => (
          <article className="ds-cases__card" key={i}>
            <Quote
              className="ds-cases__mark"
              size={28}
              strokeWidth={1.5}
              aria-hidden="true"
            />
            <blockquote className="ds-cases__quote">{c.quote}</blockquote>
            <footer className="ds-cases__by">
              <div>
                <strong>{c.author}</strong>
                <span>{c.role}</span>
              </div>
              {c.context && <span className="ds-cases__tag">{c.context}</span>}
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}
