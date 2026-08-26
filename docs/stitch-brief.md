# uradres.net — Mobile App Design Brief (for Google Stitch)

Purpose: generate the mobile app skeleton for uradres.net — a Russian B2B
marketplace of legal addresses (юридические адреса) for company registration.
Clients browse a catalog of addresses, file an application, pay, and receive
a document package. All UI text is **Russian**; use the exact strings given below.

Platform: mobile app (iOS/Android), light theme only. Style: premium B2B,
Linear-like, restrained. Indigo accent on near-white surfaces. No gradients
(one exception noted), no dark mode, no illustrations — the product sells
trust and paperwork done right.

---

## Design system

### Color

- Page background: `#fafbfc`. Cards and surfaces: `#ffffff`.
- Primary text: `#0b0a2e` (very dark indigo — never pure black).
- Muted text: `#64748b`. Card border: `#ececff` (soft, slightly cool).
- Brand / accent: indigo `#5b5bd6`; pressed/darker `#4a47c2`; deep `#3b38a3`.
- Selected filter chips fill with `#0b0a2e` (near-black indigo), NOT brand
  indigo — a selected chip must read darker than a button.
- Status colors, always background+text pairs on pill badges:
  - success `#dcfce7` / `#166534`
  - warning `#fef3c7` / `#92400e`
  - danger `#fee2e2` / `#991b1b`
  - info `#dbeafe` / `#1e40af`
  - neutral `#f1f3f6` / `#475569`
  - brand `#f0f1fd` / `#3b38a3`

### Typography

- Font: Inter. Numbers/IDs may use JetBrains Mono.
- Mobile display sizes: 30/26/22px, weight 700, tight letter-spacing (-0.03em).
- Headings: 18px and 15px, weight 600–700.
- Body: 14px; secondary 13px; captions/labels 11px UPPERCASE with +0.06em
  letter-spacing, muted color.

### Shape & spacing

- Spacing grid: 4px base (4, 8, 12, 16, 24, 32, 48).
- Radii: buttons and icon tiles 8px; inputs and cards 10px; modals 14px;
  chips and badges are full pills.
- Shadows are barely-there, with a cold indigo tint, never gray or heavy.
- Screen padding: 16px.

### Components

- **Primary button**: indigo `#5b5bd6` fill, white text, weight 600, radius 8px,
  height ~44px. Secondary: white, `#e2e6ec` border, dark text. Ghost: no fill,
  indigo text.
- **Chip (filter)**: pill, white with `#e2e6ec` border; selected — filled `#0b0a2e`,
  white text, with a small × to clear.
- **Badge (status)**: pill, 11px UPPERCASE, colors from the status pairs above.
- **Input**: white, `#e2e6ec` border, radius 10px, padding 10–12px; focus =
  indigo border + soft indigo glow ring.
- **Card**: white, `#ececff` border, radius 10px, photo on top with rounded top
  corners; if no photo — a tile with the street-name initials on an indigo
  gradient (135°, `#5b5bd6` → `#8b87ff`; the only gradient in the system).
- **Stat block**: big number 26–28px weight 700, under it an 11px UPPERCASE
  muted label.

---

## App structure

Two audiences in one app:

1. **Public / logged out** — catalog, address details, application form, login.
2. **Client cabinet** (after login) — bottom tab bar: Заявки · Календарь · Чаты.

(An owner cabinet exists too — tabs Заявки · Адреса · Задачи · Календарь · Чаты —
but generate the client side first; owner screens reuse the same patterns.)

---

## Screens

### 1. Каталог (home, logged out)

- Top bar: logo «uradres.net», bell-less; right side «Войти» (ghost button).
- Hero: H1 «Маркетплейс юридических адресов. За 1 день.» (30px), subtitle
  «Проверенные собственники, готовый комплект документов с гарантийным
  письмом и выпиской ЕГРН.»
- Three promise rows with check icons: «Возврат средств при отказе налоговой»,
  «Замена адреса без доплат», «Документы соответствуют требованиям ФНС».
- Stat row (2×2): «26 · АДРЕСОВ В КАТАЛОГЕ», «10 · ИФНС В КАТАЛОГЕ»,
  «10 · ГОРОДОВ», «6 и 11 · МЕСЯЦЕВ АРЕНДЫ».
- Filter block: search field «По адресу или ИФНС», selects Регион → Город →
  ИФНС (cascade), segmented control for term «6 мес. / 11 мес.», price range,
  toggle «С почтой». Quick chips: «Дешевле 20 000 ₽», «Дешевле 30 000 ₽»,
  «С почтой». Result counter: «Найдено 26 адресов».
- Address cards, 1 per row: photo (or initials tile), title
  «г. Москва, ул. Академика Королёва, д. 13, стр. 1», subtitle
  «офис 214 · ИФНС № 46», term segmented 11/6 мес., option line
  «+ почта 4 000 ₽/мес», price «28 000 ₽ / за 11 мес.» (price is the loudest
  element after the title), primary button «Оформить заявку», secondary
  «Подробнее», compare checkbox «Сравнить».
- Pagination: «← Назад · Страница 1 из 2 · Вперёд →».

### 2. Карточка адреса

- Photo gallery with thumbnails; fallback initials tile.
- Address as title, then meta rows: ИФНС, офис, срок аренды.
- Price block for 6 and 11 months; extra services as tags («Почтовое
  обслуживание — 3 000 ₽/мес»).
- Included services list with checks; trust line (owner rating ★ 4.8 and
  review count); map preview; reviews section.
- Sticky bottom CTA: «Оформить заявку».

### 3. Заявка (application form)

- Form: «Название компании», «Контактное лицо», «Телефон», «E-mail»,
  segmented «Срок аренды: 6 мес. / 11 мес.», application type radio:
  «Регистрация новой компании» / «Смена адреса действующей», consent
  checkbox with link «Согласие на обработку персональных данных».
- Primary button «Отправить заявку». After submit — success screen: icon,
  «Заявка отправлена», text about owner confirmation, button «В кабинет».

### 4. Вход

- Fields «E-mail», «Пароль», primary «Войти», ghost «Зарегистрироваться»,
  link «Забыли пароль?».

### 5. Кабинет клиента — Заявки (default tab)

- Header: «Заявки», subtitle «Всего заявок: 3».
- Application cards: address line, company name, status badge, date, price.
  Status badges (label → tone): «Черновик» neutral, «Ожидает оплату» brand,
  «Оплачена» success, «Проверка администратора» info, «Нужны уточнения»
  warning, «Передана собственнику» warning, «Готовятся документы» info,
  «Готова к выдаче» success, «Активна» success, «Завершена» success,
  «Отменена» neutral, «Спор» danger, «Истекла» warning.
- Tapping opens application detail: status timeline (dots + rail), document
  list with download rows (DOCX/PDF icons, file size), payment block with
  «Оплатить» when status = «Ожидает оплату», chat shortcut button
  «Чат по заявке».

### 6. Кабинет клиента — Календарь

- Month view; marked dates = lease expirations and deadlines. Below the
  calendar — event list rows: date, address, label like «Окончание аренды»,
  status badge «Скоро» warning / «Просрочено» danger.

### 7. Кабинет клиента — Чаты

- Chat list: rows with address as title, last message preview, time, unread
  count badge (indigo pill). Empty state: «Пока нет сообщений».
- Chat screen: bubbles — own messages right, indigo-tinted `#f0f1fd`
  background; other side left, `#f1f3f6`; author label 11px above bubble
  («Собственник», «Поддержка»), time 11px muted. Attachment rows with file
  name and size. Compose bar: input + paperclip + send (indigo circle).

### 8. Профиль / настройки (from avatar in header)

- Rows: e-mail with verification badge, «Уведомления», «Документы»,
  «Выйти». Footer legal line: «ООО «Юрадрес.Нет» · ИНН 7751397240».

---

## Navigation

- Logged out: stack navigation (catalog → address → application → login).
- Logged in: bottom tab bar with 3 tabs — «Заявки» (folder icon),
  «Календарь» (calendar icon), «Чаты» (message icon, unread dot). Icons:
  lucide style, 1.5–2px stroke, no fills.
- Top bar inside cabinet: screen title left, avatar right.

## Tone

Calm, legal-grade, dense with facts but airy in layout. Everything aligns to
the 4px grid. One accent color; status colors appear only in badges and small
hints, never as large surfaces.
