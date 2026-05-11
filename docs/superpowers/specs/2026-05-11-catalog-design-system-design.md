# Design Spec: Public Catalog + Design System

**Date:** 2026-05-11
**Project:** legal_address_service (FastAPI + React+Vite+TS, framer-motion installed)
**Scope:** Design system tokens + components + showcase screen (public catalog)
**Showcase screen:** `/marketplace` — public address catalog
**Status:** Sections 1–4 approved. Section 5 (Implementation phases) — pending in next session.

---

## 0. Принятые решения (от пользователя)

| Decision | Value | Notes |
|---|---|---|
| Scope | C — design system + 1 экран | Не редизайн всех 4 поверхностей сразу |
| Showcase screen | A — публичный каталог `/marketplace` | Самый «лицевой» экран |
| Visual style | A — Premium B2B (Linear/Stripe-like) | Не editorial, не brutalist, не warm minimalist |
| Palette | A — Indigo (Linear) | Светлый mode, indigo+violet акцент |
| Card visuals | D — реальные фото зданий, owner uploads | Не текст, не плейсхолдер, не карта |
| Direction within style | 1 — Pragmatic Linear | Не editorial wow, не power-user dense |

### Убранные элементы (по правкам пользователя)
- Бейдж `success` «Свободно» — удалён (это дефолт, лишний шум)
- Бейдж `danger` «Занято» — удалён (занятые адреса в публичный каталог не попадают)
- На карточке статус-бейдж теперь только опционально — `«Новый адрес»` (overlay) для свежедобавленных, `«На модерации»` только для admin

---

## 1. Design Tokens

### 1.1 Палитра

#### Indigo (бренд · CTA, ссылки, фокус)
| Step | Hex | Step | Hex |
|---|---|---|---|
| 50 | `#F0F1FD` | 500 | `#5B5BD6` ⭐ |
| 100 | `#DDE0FA` | 600 | `#4A47C2` |
| 200 | `#BCC1F5` | 700 | `#3B38A3` |
| 300 | `#9AA1EB` | 800 | `#2B2980` |
| 400 | `#7D83E0` | 900 | `#1A1958` |
| | | 950 | `#0B0A2E` (text/dark bg) |

#### Slate (нейтрали · текст, фон, границы)
| Step | Hex | Step | Hex |
|---|---|---|---|
| 50 | `#FAFBFC` (page bg) | 500 | `#64748B` (secondary text) |
| 100 | `#F1F3F6` | 600 | `#475569` |
| 200 | `#E2E6EC` (borders) | 700 | `#334155` |
| 300 | `#CBD1DA` | 800 | `#1E293B` |
| 400 | `#9BA3B1` | 900 | `#0F172A` |
| | | 950 | `#020617` |

> Нюанс: для текста + decorative elements использовать `#0B0A2E` (Indigo-950), для page bg `#FAFBFC` (Slate-50), для card borders `#ECECFF` (между Indigo-50 и Slate-100, мягче).

#### Семантические
| Token | Bg | Text | Use |
|---|---|---|---|
| `success` | `#DCFCE7` | `#166534` | «Новый адрес» badge |
| `warning` | `#FEF3C7` | `#92400E` | «На модерации» (admin) |
| `danger` | `#FEE2E2` | `#991B1B` | Error state, danger button |
| `info` | `#DBEAFE` | `#1E40AF` | «Новое» badge |
| `neutral` | `#F1F3F6` | `#475569` | «Архив» badge |
| `brand` | `#F0F1FD` | `#3B38A3` | «Премиум» badge |

### 1.2 Типографика

**Шрифты:** Inter (variable, sans-serif, кириллица, tabular figures) + JetBrains Mono (monospace для номеров договоров/ИНН).

| Token | Size | Line | Tracking | Weight | Usage |
|---|---|---|---|---|---|
| `display-xl` | 48 | 1.02 | -0.04em | 700 | Hero h1 |
| `display-lg` | 36 | 1.05 | -0.03em | 700 | Section title |
| `display-md` | 28 | 1.1 | -0.025em | 700 | — |
| `heading-lg` | 22 | 1.15 | -0.02em | 600 | Page title |
| `heading-md` | 18 | 1.2 | -0.015em | 600 | Card title |
| `heading-sm` | 15 | 1.25 | -0.01em | 600 | Small heading |
| `body-md` | 14 | 1.5 | 0 | 400 | Body |
| `body-sm` | 13 | 1.5 | 0 | 400 | Secondary body |
| `label` | 11 | 1.2 | 0.06em | 500 | Uppercase labels |
| `mono` | 12 | 1.5 | 0 | 500 | Numbers, IDs |

### 1.3 Spacing (база 4px)

`1=4` · `2=8` · `3=12` · `4=16` · `6=24` · `8=32` · `12=48` · `16=64` · `20=80`

### 1.4 Радиусы

| Token | Px | Use |
|---|---|---|
| `sm` | 4 | Code badges |
| `md` | 8 | Buttons (icon), iconbox-sm |
| `lg` | 10 | Cards, inputs ⭐ |
| `xl` | 14 | Modals, big cards |
| `pill` | 9999 | Buttons, chips, badges |

### 1.5 Тени

| Token | Value |
|---|---|
| `shadow-sm` | `0 1px 0 rgba(11,10,46,.04)` |
| `shadow-md` | `0 1px 3px rgba(11,10,46,.06), 0 1px 2px rgba(11,10,46,.04)` |
| `shadow-lg` | `0 4px 12px rgba(11,10,46,.08), 0 2px 4px rgba(11,10,46,.04)` |
| `shadow-xl` | `0 18px 40px rgba(11,10,46,.10), 0 6px 12px rgba(11,10,46,.06)` (hover) |

### 1.6 Motion (framer-motion)

| Token | Duration | Easing | Use |
|---|---|---|---|
| `fast` | 120ms | ease-out | Hover, focus, chip activation |
| `base` | 200ms | ease-out | Card appear, state transitions |
| `slow` | 320ms | cubic-bezier(.2,.8,.2,1) | Hero entrance, stagger, page transitions |

Все анимации respect `prefers-reduced-motion: reduce` (мгновенно, без transform).

---

## 2. Component Primitives

### 2.1 Buttons

| Variant | Bg | Color | Hover |
|---|---|---|---|
| `primary` | `#5B5BD6` | `#FFF` | `#4A47C2` + lift -1px + shadow `rgba(91,91,214,.3)` |
| `secondary` | `#FFF` | `#0B0A2E` + border `#E2E6EC` | bg `#FAFBFC`, border `#CBD1DA` |
| `ghost` | transparent | `#5B5BD6` | bg `#F0F1FD` |
| `danger` | `#FEE2E2` | `#991B1B` | bg `#FECACA` |

**Sizes:** `sm` (12px text, 6×12 padding) · `md` (13px, 9×16) · `lg` (14px, 12×22) · `icon` (32×32, radius 8).
**Radius:** pill (9999) для всех кроме icon-only.
**Disabled:** opacity 0.5, pointer-events none.

### 2.2 Chips (filter)

Pill-форма, padding 6×12, font-size 12, weight 500.
- **Idle:** bg `#FFF`, border `#E2E6EC`, color `#0B0A2E`. Hover → border `#CBD1DA`.
- **Active:** bg `#0B0A2E`, color `#FFF`. Опционально × для снятия (opacity 0.6).

### 2.3 Badges (status)

Pill, padding 3×9, font-size 11, weight 600, uppercase, letter-spacing 0.04em. Опциональная точка-индикатор 5×5 цвета currentColor.

| Token | Bg | Color | Label |
|---|---|---|---|
| `new` | `#DCFCE7` | `#166534` | «Новый адрес» (свежеопубликованный, < 7 дней) |
| `warning` | `#FEF3C7` | `#92400E` | «На модерации» (admin only) |
| `info` | `#DBEAFE` | `#1E40AF` | «Новое» |
| `neutral` | `#F1F3F6` | `#475569` | «Архив» |
| `brand` | `#F0F1FD` | `#3B38A3` | «Премиум» |

**Удалены:** `success` «Свободно», `danger` «Занято».

### 2.4 Inputs & Select

**Input:** bg `#FFF`, border `#E2E6EC`, radius `lg` (10), padding 10×12, gap 8 (для иконки), min-width 280.
- Hover: border `#CBD1DA`
- Focus: border `#5B5BD6`, ring `0 0 0 3px rgba(91,91,214,.15)`
- Error: border `#EF4444`, ring `0 0 0 3px rgba(239,68,68,.12)`, текст ошибки 11px `#991B1B` снизу
- Внутренний `<input>`: 13px, color `#0B0A2E`, placeholder `#9BA3B1`

**Select trigger:** визуально как input, padding 9×12, стрелка `▾` цвета `#9BA3B1`.

### 2.5 Stat block

Группа stat-блоков (для hero), разделители — тонкие вертикальные линии `1px #E2E6EC`, padding 0 24px (первый — без border-left + padding-left 0).
- Number: `display-md` (28px) → на десктопе, `display-md` (24px) в нав-стате
- Label: `label` (11px uppercase letter-spacing 0.06em color #64748B)

### 2.6 Iconbox / Avatar

Контейнер с initials или иконкой, gradient `linear-gradient(135deg,#5B5BD6,#8B87FF)`, color #FFF, weight 700.
- `sm` 28×28 radius 6 font 11
- `md` 40×40 radius 8 font 13 ⭐
- `lg` 56×56 radius 10 font 16

### 2.7 Address Card

**Структура:** image (top) + body (bottom).

```
┌──────────────────────┐
│  [фото 4:3]          │  ← optional badge overlay (top-left)
│                      │  ← optional photo-count (bottom-right)
├──────────────────────┤
│ ул. Тверская, 7…    │  l1: heading-md 14px weight 600
│ ИФНС № 46 · 11 мес  │  l2: body-sm 12px color #64748B
│                      │
│ от 30 000 ₽   →     │  price 16 weight 700 #5B5BD6 + ghost-btn-sm
└──────────────────────┘
```

- Container: bg `#FFF`, border `1px #ECECFF`, radius `lg` (10), shadow-sm
- Hover (motion `base` 200ms): translateY -3px + shadow-xl + border `#DDE0FA`
- Image: aspect-ratio 4/3, может содержать badge-overlay (top:10 left:10) и photo-count (bottom:10 right:10)
- Body padding: 14×16 (вместо 12×14 — для desktop)
- Cursor: pointer; вся карточка — link

**Состояния (см. раздел 4):** `no-photo` (gradient + initials) · `loading` (blur) · `loaded` · `multi-photo`.

**Бейдж overlay positions:**
- `«Новый адрес»` (badge-new) — top-left, всегда поверх фото
- `«На модерации»` (badge-warning) — top-left, только в admin-вьюхе

### 2.8 Link

Inline link: color `#5B5BD6`, weight 500, no underline; hover: underline (border-bottom 1px). Used in body copy и navigation.

---

## 3. Catalog Screen Layout + States

### 3.1 Top nav

- Bg `#FFF`, border-bottom `1px #ECECFF`, padding 14×32
- Left: logo (iconbox-sm `mark` + name 18px weight 700)
- Center: links 13px color `#475569`, gap 24, hover → `#0B0A2E`
- Right: ghost-btn «Войти» + primary-btn «Подобрать адрес»

### 3.2 Hero

- Container: padding 48×32×32, max-width 1180, centered
- H1: `display-xl` (48), max-width 720, акцент-курсивная фраза в `#5B5BD6` (например `<em>За 1 день.</em>`)
- Sub: `body-md` 16px color `#64748B`, max-width 580, margin-top 18
- Stat-row: padding-top 28, border-top `1px #ECECFF`, margin-top 32 — 4 stat-блока с разделителями

### 3.3 Filter bar

- Container: padding 24×32, max-width 1180, gap 12, flex-wrap
- Composition: search input (флекс растягивается) + region chips (Москва/МО) + 3 select-trigger (ИФНС, Срок, Цена) + corr-chip
- Активные чипы — с × для снятия

### 3.4 Result counter

- Padding 8×32, max-width 1180
- Left: «Показано **1–18** из **2 412** адресов»
- Right: select-trigger «Сортировка: новые сначала ▾»

### 3.5 Grid

- Container: padding 0×32×48, max-width 1180
- 3-col grid (gap 18) на desktop ≥1024
- 2-col на tablet 640–1023
- 1-col на mobile <640
- Card layout — см. 2.7

### 3.6 Pagination

- Centered button «Загрузить ещё 18 адресов» (secondary-btn-md)
- Fallback на классическую пагинацию если результатов >200

### 3.7 States

**Loading skeleton:**
- Hero и filter-bar с реальным контентом (структура стоит сразу)
- Grid: 6 skel-карточек с `@keyframes shimmer 1.4s linear infinite` (200→-200px), bg gradient `#F1F3F6 → #ECECFF → #F1F3F6`

**Empty (нет результатов по фильтру):**
- Filter-bar с активными чипами + ghost-btn «Сбросить фильтры»
- Empty-state по центру (max-width 480): icon ⌕ в `#F0F1FD`/`#5B5BD6` (56×56 radius 14) + h3 «По заданным фильтрам адресов нет» + p-подсказка с цифрами каталога + primary-btn «Сбросить фильтры»

**Error (бэкенд недоступен):**
- Empty-state структура, но icon ⚠ в `#FEE2E2`/`#991B1B`
- H3 «Не удалось загрузить каталог»
- Two CTA: secondary «Связаться с поддержкой» + primary «Обновить страницу»

### 3.8 Mobile (<640px)

- Topnav: hamburger-btn (secondary-sm «☰») вместо линков
- Hero: H1 30px, 2 stat-блока (вместо 4)
- Filter bar: search input + кнопка «Фильтры (3)» (открывает drawer)
- Grid: 1-col, карточки full-width

---

## 4. Photo Strategy

### 4.1 Состояния карточки

| State | Image area | Note |
|---|---|---|
| `no photo` | gradient `linear-gradient(135deg,#5B5BD6,#3B38A3)` + initials улицы (1–2 буквы) 36px weight 700 + ИФНС снизу 10px mono | Адрес опубликован, owner не загрузил фото |
| `loading` | тот же фон, что у фото, но `filter:blur(8px)` | Native lazy + progressive jpg/webp |
| `loaded · 1` | фото 4:3, опц. overlay-badge сверху-слева | Default |
| `loaded · multi` | фото + индикатор `📷 N` справа-снизу (rgba(11,10,46,0.75) + blur backdrop) | Multi-photo address |

### 4.2 Backend модель: `address_photos`

```python
class AddressPhoto(UUIDPKMixin, Base):
    __tablename__ = "address_photos"
    __table_args__ = (
        Index(
            "uniq_main_photo_per_address",
            "address_id", unique=True,
            postgresql_where="is_main = true",
        ),
        Index("ix_address_photos_position", "address_id", "position"),
    )

    address_id          = FK addresses.id ON DELETE CASCADE
    file_url            = Text NOT NULL  # /storage/photos/<sha>.jpg
    thumbnail_url       = Text           # /storage/photos/<sha>_thumb.jpg (640x480)
    file_sha256         = Text NOT NULL  # дедуп
    width, height       = Integer NOT NULL  # анти-CLS
    position            = Integer NOT NULL  # порядок в галерее
    is_main             = Boolean default false  # одна true на адрес
    moderation_status   = Text NOT NULL CHECK IN ('pending','approved','rejected')
    moderation_comment  = Text
    uploaded_by         = FK users.id
    uploaded_at         = DateTime
```

### 4.3 Upload flow (owner)

1. Owner: `POST /owner/addresses/{id}/photos` — multipart, до 10 файлов за раз, `jpg|png|webp` ≤ 8 MB
2. Backend: mime-валидация (Pillow), ресайз 1600px (main) + 640px (thumb), сохранение в `storage/photos/<sha256>.jpg`, запись `moderation_status='pending'`
3. Backend: создаёт `ApplicationEvent` для admin'ов (kind может быть новый `photo_pending` или переиспользовать существующий `comment_added` с payload — TBD на этапе implementation)
4. Admin: `GET /admin/photos?status=pending` → список с миниатюрами; `POST /admin/photos/{id}/approve|/reject` (с комментарием при reject)
5. **Approve:** `moderation_status='approved'`. Если у адреса нет main — это фото становится `is_main=true`. Появляется в публичном API.
6. **Reject:** `moderation_status='rejected'`, комментарий → owner notification. Owner может перезагрузить.

### 4.4 Display (frontend)

- На карточке каталога — только `thumbnail_url` (640px) main-фото. Один запрос на адрес.
- Loading: native `<img loading="lazy">` + CSS blur поверх low-q `background-image`. Без blurhash в MVP.
- Без фото — fallback gradient + инициалы (см. 4.1).
- Multi: индикатор `📷 N` правый-нижний угол.
- На `<img>` всегда `width/height` атрибуты против CLS.

### 4.5 Миграция и совместимость

- Alembic `0006_address_photos`: новая таблица + индексы + check для `moderation_status`
- Public schema `AddressRead` ← добавить **опциональные** `main_photo_url: Optional[str]` и `photo_count: int = 0` — старые клиенты не сломаются
- Owner и Admin схемы — новый роутер `app/routers/address_photos.py`
- Демо-сид (`marketplace_seed.py`): кладёт по 1 плейсхолдеру на каждый адрес (готовый JPG копируется в storage)
- `requirements.txt` += `Pillow`

---

## 5. Implementation Phases

**Status:** TODO в следующей сессии (новый чат).

Ожидаемая разбивка (черновик, требует утверждения):

1. **Phase 1: Design tokens + primitives** — собрать в `frontend/src/styles.css` (или extract в `frontend/src/design/tokens.css` + `frontend/src/design/components.css`); только примитивы, без реалий каталога.
2. **Phase 2: Catalog screen без фото** — переделать `frontend/src/publicCatalog.tsx` под новый layout (hero/filters/grid/states) на текущих fallback-плейсхолдерах. Уже даёт wow.
3. **Phase 3: Photo backend** — модель, миграция, owner upload + admin moderation API. Pillow в reqs. Тесты.
4. **Phase 4: Photo frontend** — owner-дашборд аплоадер, admin-модерация UI, публичный каталог берёт `main_photo_url` из API.
5. **Phase 5: Animations** — framer-motion: hero entrance (slow), grid stagger (slow), card hover lift (fast→base).

---

## 6. Mockup References (визуальный companion)

Все мокапы лежат в `.superpowers/brainstorm/23735-1778480909/content/`:

| File | Section |
|---|---|
| `visual-style.html` | Style direction (4 вариантов) — выбрана A. Premium B2B |
| `palette.html` | Palette (4 вариантов) — выбрана A. Indigo |
| `approaches.html` | 3 направления (Pragmatic / Editorial / Power-user) — выбран 1. Pragmatic |
| `tokens.html` | Раздел 1: Design tokens |
| `components.html` | Раздел 2: Component primitives v1 |
| `components-v2.html` | Раздел 2: Primitives v2 (после правок «Новый адрес» / убрали «Свободно/Занято») |
| `catalog-screen.html` | Раздел 3: Catalog screen + states |
| `photos.html` | Раздел 4: Photo strategy |

Для просмотра — `bash /Users/sergejgorgidzanov/.claude/skills/brainstorming/scripts/start-server.sh --project-dir /Users/sergejgorgidzanov/legal_address_service`

---

## 7. Open Questions for Next Session

- [ ] Phase 5 (animations) детали: какие именно motion patterns, `LazyMotion`/no, `useReducedMotion` обработка
- [ ] Photo upload: новый event kind для admin notification (`photo_pending`?) или payload в `comment_added`
- [ ] Multi-photo gallery на detail-странице адреса — нужна ли в этом scope или отдельный спек
- [ ] Иконки: lucide-react уже стоит. Заменить эмодзи 📷, ⌕, ⚠, ▾ → на lucide компоненты
- [ ] Responsive breakpoints: ≥1024 / 640–1023 / <640 — подтвердить или взять Tailwind defaults
- [ ] Тёмный mode: вне scope MVP или нужно опционально
