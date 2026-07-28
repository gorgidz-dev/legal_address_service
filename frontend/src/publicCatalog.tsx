import {
  AlertTriangle,
  ArrowRight,
  ArrowUp,
  Building2,
  Camera,
  CheckCircle2,
  ChevronRight,
  FileText,
  KeyRound,
  Loader2,
  Mail,
  MapPin,
  Menu,
  Search,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AddressChatPanel } from "./AddressChatPanel";
import { api } from "./api";
import { PhoneInput } from "./PhoneInput";
import { HomeConfigurator } from "./sections/HomeConfigurator";
import { HomeFAQ } from "./sections/HomeFAQ";
import { HomeForOwners } from "./sections/HomeForOwners";
import { HomeCases } from "./sections/HomeCases";
import { HomeSteps } from "./sections/HomeSteps";
import { StarRating } from "./sections/StarRating";
import { AddressReviews } from "./sections/AddressReviews";
import { useModalDismiss } from "./useModalDismiss";
import type { LegalDoc } from "./router";
import { AddressMapModal } from "./sections/AddressMapModal";
import type {
  AddressChat,
  CurrentUser,
  GeoRegion,
  ProviderConnectionRequestCreate,
  PublicAddress,
  PublicClientApplicationCreate,
} from "./types";

type PublicCatalogProps = {
  canBootstrap: boolean;
  currentUser: CurrentUser | null;
  onAuthenticated: (user: CurrentUser) => void;
  onLoginClick: () => void;
  /** Открыт ли каталог из кабинета — возврат назад. */
  onOpenDashboard?: () => void;
  /**
   * Открытая карточка адреса живёт в URL (/address/<id>): ссылкой на объект
   * можно поделиться, а «Назад» в браузере закрывает карточку, а не уводит
   * со страницы.
   */
  openAddressId: string | null;
  onOpenAddress: (id: string | null) => void;
  /** Открыть правовой документ (подвал и ссылки под формами). */
  onOpenLegal: (doc: LegalDoc) => void;
};

type CatalogSort = "default" | "price_asc" | "price_desc" | "newest";

type CatalogFilters = {
  query: string;
  city: string;
  fnsNumber: string;
  // Гео-каскад: Регион → Город → ИФНС (структурный фильтр через fns_offices).
  region: string;
  geoCity: string;
  fnsOfficeId: string;
  // Диапазон цены за 11 мес. (строки — из числовых инпутов «от»/«до»).
  priceFrom: string;
  priceTo: string;
  sort: CatalogSort;
  withCorr: boolean;
  /**
   * Пресет верхней границы цены. Раньше это был булев `budgetUnder30k`; чтобы
   * добавить «дешевле 20 000» вторым флагом, пришлось бы решать, что делать
   * при обоих включённых. Ссылки со старым `budget=lt30` продолжают работать.
   */
  budgetPreset: "" | "lt20" | "lt30";
  premium11: boolean;
};

const BUDGET_PRESET_VALUES: Record<Exclude<CatalogFilters["budgetPreset"], "">, number> = {
  lt20: 20000,
  lt30: 30000,
};

const initialFilters: CatalogFilters = {
  query: "",
  city: "",
  fnsNumber: "",
  region: "",
  geoCity: "",
  fnsOfficeId: "",
  priceFrom: "",
  priceTo: "",
  sort: "default",
  withCorr: false,
  budgetPreset: "",
  premium11: false,
};

/**
 * Пункты верхнего меню. Один список на десктоп и на мобильный бургер, чтобы
 * они не разъезжались.
 *
 * «Для собственников» ведёт в секцию, а не сразу в форму: раньше клик открывал
 * модалку минуя описание условий, а Ctrl+клик по той же ссылке уводил в секцию —
 * поведение зависело от того, как нажали.
 */
const MENU_LINKS: Array<{ href: string; label: string }> = [
  { href: "#catalog", label: "Каталог" },
  { href: "#how", label: "Как это работает" },
  { href: "#owners", label: "Для собственников" },
];

const VALID_SORTS: CatalogSort[] = ["default", "price_asc", "price_desc", "newest"];

/** Минимальная длина текстового запроса — поиск стартует с 3-го символа. */
const MIN_QUERY_LEN = 3;

/** Filters → query string. Записываем только не-дефолтные поля, чтобы URL был чистым. */
function filtersToQueryString(f: CatalogFilters): string {
  const p = new URLSearchParams();
  if (f.query.trim()) p.set("q", f.query.trim());
  if (f.city !== initialFilters.city) p.set("city", f.city);
  if (f.fnsNumber) p.set("ifns", f.fnsNumber);
  if (f.region) p.set("region", f.region);
  if (f.geoCity) p.set("gcity", f.geoCity);
  if (f.fnsOfficeId) p.set("office", f.fnsOfficeId);
  if (f.priceFrom) p.set("pf", f.priceFrom);
  if (f.priceTo) p.set("pt", f.priceTo);
  if (f.sort !== "default") p.set("sort", f.sort);
  if (f.withCorr) p.set("corr", "1");
  if (f.budgetPreset) p.set("budget", f.budgetPreset);
  if (f.premium11) p.set("tier", "premium");
  return p.toString();
}

/** Query string → filters. Невалидные значения мягко падают к дефолту. */
function filtersFromQueryString(search: string): CatalogFilters {
  const p = new URLSearchParams(search);
  const sort = p.get("sort");
  return {
    query: p.get("q") ?? "",
    city: p.get("city") ?? initialFilters.city,
    fnsNumber: p.get("ifns") ?? "",
    region: p.get("region") ?? "",
    geoCity: p.get("gcity") ?? "",
    fnsOfficeId: p.get("office") ?? "",
    priceFrom: p.get("pf") ?? "",
    priceTo: p.get("pt") ?? "",
    sort: sort && (VALID_SORTS as string[]).includes(sort) ? (sort as CatalogSort) : "default",
    withCorr: p.get("corr") === "1",
    budgetPreset: p.get("budget") === "lt20" ? "lt20" : p.get("budget") === "lt30" ? "lt30" : "",
    premium11: p.get("tier") === "premium",
  };
}

type CardOptions = { term: 6 | 11; corr: boolean };
const defaultCardOptions: CardOptions = { term: 11, corr: false };

/** Ключ хранения выбора по карточкам — на вкладку, не навсегда. */
const CARD_OPTIONS_KEY = "ds:card-options";

function readCardOptions(): Record<string, CardOptions> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(CARD_OPTIONS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (!parsed || typeof parsed !== "object") return {};
    const result: Record<string, CardOptions> = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      const option = value as Partial<CardOptions> | null;
      if (!option) continue;
      result[id] = {
        term: option.term === 6 ? 6 : 11,
        corr: option.corr === true,
      };
    }
    return result;
  } catch {
    // Мусор в хранилище не должен ронять каталог.
    return {};
  }
}

function writeCardOptions(value: Record<string, CardOptions>): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(CARD_OPTIONS_KEY, JSON.stringify(value));
  } catch {
    /* приватный режим / переполнение — выбор просто не переживёт перезагрузку */
  }
}

// Fallback на случай, если /marketplace/fns-options ещё не загрузился
// или пуст. ИФНС Москвы: 1–31, 33–36, 43, 51.
const MOSCOW_FNS_NUMBERS: number[] = [
  ...Array.from({ length: 31 }, (_, i) => i + 1),
  33, 34, 35, 36,
  43,
  51,
];

// "Шумовые" слова, которые пользователи часто пишут в поиске, но они
// не несут смысла для матчинга адреса: "ул.", "д.", "г.", "офис" и т.д.
// Удаляем и из запроса, и из haystack — оба становятся "тверская 7" вместо
// "ул. Тверская д. 7" → совпадает, даже если пользователь не угадал формат.
const SEARCH_NOISE_RE =
  /\b(?:г|город|ул|улица|пер|переулок|пр|пр-т|проспект|просп|пл|площадь|ш|шоссе|наб|набережная|б-р|бульвар|туп|тупик|линия|алл|аллея|тракт|мкр|микрорайон|д|дом|корп|корпус|стр|строение|вл|владение|лит|литера|пом|помещение|оф|офис|комн|комната|кв|квартира|этаж|эт)\.?(?=\s|$|,)/giu;

/**
 * Нормализация для поискового сопоставления. Не для отображения.
 *
 * - lowercase
 * - ё → е (часто пишут по-разному: "артем"/"артём")
 * - удаление "ул.", "д.", "г." и пр. (см. SEARCH_NOISE_RE)
 * - схлопывание пробелов и знаков препинания
 */
function normalizeSearchText(s: string): string {
  return s
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(SEARCH_NOISE_RE, " ")
    .replace(/[.,;:!?()«»"'–—\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Подсветка вхождений `query` в `text`. Учитывает ё/е (например, запрос
 * "артем" подсветит "Артём"). Если query пустой — возвращает текст как есть.
 */
// Без флага `g` — чтобы `.test()` был stateless при фильтрации слов запроса.
const SEARCH_NOISE_TEST_RE = new RegExp(SEARCH_NOISE_RE.source, "iu");

function HighlightMatch({ text, query }: { text: string; query: string }) {
  const q = query.trim();
  if (!q) return <>{text}</>;
  // Разбиваем запрос на слова — подсвечиваем каждое (≥2 символа, не "шум").
  const words = q
    .split(/\s+/)
    .filter((w) => w.length >= 2 && !SEARCH_NOISE_TEST_RE.test(w));
  if (!words.length) return <>{text}</>;
  // ё/е тoлерантность: [её] вместо буквы (запрос "артем" → подсветит "Артём").
  const pattern = words
    .map((w) => escapeRegExp(w).replace(/[её]/gi, "[её]"))
    .join("|");
  const re = new RegExp(`(${pattern})`, "gi");
  // split с capturing group: odd-индексы = совпадения, even = разделители.
  const parts = text.split(re);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="ds-search-hit">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

type OwnerRequestForm = {
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  city: string;
  address_count: string;
  comment: string;
};

const initialOwnerRequestForm: OwnerRequestForm = {
  company_name: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  city: "",
  address_count: "",
  comment: "",
};

type ClientApplicationForm = {
  type: "initial_registration" | "address_change";
  planned_client_name: string;
  client_inn: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  password: string;
  term_months: 6 | 11;
  has_correspondence_service: boolean;
  payer_type: "individual" | "juridical";
};

const initialClientApplicationForm: ClientApplicationForm = {
  type: "initial_registration",
  planned_client_name: "",
  client_inn: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  password: "",
  term_months: 11,
  has_correspondence_service: false,
  payer_type: "individual",
};

const NEW_ADDRESS_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(amount);
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function streetInitials(fullAddress: string): string {
  const match = fullAddress.match(
    /(?:ул\.|улица|просп\.|проспект|пр\.|пер\.|переулок|наб\.|набережная|пл\.|площадь|ш\.|шоссе|бул\.|бульвар)\s*([А-Яа-яЁё-]+)/i,
  );
  const word = match?.[1] ?? fullAddress.replace(/^[^А-Яа-яЁё]+/, "").split(/[\s,]/)[0] ?? "АД";
  return word.slice(0, 2).toUpperCase();
}

function isRecent(createdAt: string): boolean {
  const ts = Date.parse(createdAt);
  if (!Number.isFinite(ts)) return false;
  return Date.now() - ts <= NEW_ADDRESS_WINDOW_MS;
}

const SERVICE_KIND_LABEL: Record<string, string> = {
  guarantee_letter: "Гарантийное письмо",
  lease_agreement: "Договор аренды",
  owner_confirmation: "Подтверждение собственника",
  door_sign: "Табличка на входе",
  mail_reception: "Приём почты",
  fns_visit_photo: "Фотофиксация приёма ФНС",
  phone_answering: "Звонки",
  visitor_reception: "Приём посетителей",
};
const SERVICE_DOCUMENTS = new Set([
  "guarantee_letter",
  "lease_agreement",
  "owner_confirmation",
]);
function serviceLabel(kind: string): string {
  return SERVICE_KIND_LABEL[kind] ?? kind;
}

const heroStaggerVariants: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08, delayChildren: 0.05 },
  },
};

const heroChildVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.32, ease: [0.2, 0.8, 0.2, 1] } },
};

const gridStaggerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05 } },
};

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2, ease: "easeOut" } },
};

export default function PublicCatalog({
  canBootstrap,
  currentUser,
  onAuthenticated,
  onLoginClick,
  onOpenDashboard,
  openAddressId,
  onOpenAddress,
  onOpenLegal,
}: PublicCatalogProps) {
  const reduceMotion = useReducedMotion();
  const motionVariants = reduceMotion ? undefined : heroStaggerVariants;
  const childMotion = reduceMotion ? undefined : heroChildVariants;
  const gridMotion = reduceMotion ? undefined : gridStaggerVariants;
  const cardMotion = reduceMotion ? undefined : cardVariants;

  const [filters, setFilters] = useState<CatalogFilters>(() =>
    typeof window !== "undefined"
      ? filtersFromQueryString(window.location.search)
      : initialFilters,
  );
  const [addresses, setAddresses] = useState<PublicAddress[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(() => {
    if (typeof window === "undefined") return 1;
    const p = new URLSearchParams(window.location.search).get("page");
    return p && /^\d+$/.test(p) ? Math.max(1, parseInt(p, 10)) : 1;
  });
  const PAGE_SIZE = 24;
  /** Потолок выборки для карты — совпадает с максимумом page_size на бэке. */
  const MAP_MAX_ADDRESSES = 100;
  const [fnsOptions, setFnsOptions] = useState<
    { fns_number: number; fns_city: string | null; count: number }[]
  >([]);
  const [geoTree, setGeoTree] = useState<GeoRegion[]>([]);
  /**
   * Размер всего каталога — для счётчиков первого экрана.
   *
   * Считать их по `addresses` нельзя: там лежит текущая страница выдачи, а не
   * каталог. На проде это давало «24 адреса в каталоге» при 26 опубликованных
   * (PAGE_SIZE = 24) — и цифра ещё и менялась при любом фильтре, хотя подпись
   * обещает каталог целиком. Именно с этого экрана переписаны цифры в
   * замечаниях заказчика.
   */
  const [catalogTotal, setCatalogTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // Дебаунс текстового запроса. UI обновляется мгновенно (filters.query), а на
  // бэк уходит с задержкой 200ms. Поиск стартует с 3-го символа: запрос
  // короче 3 знаков уходит как пустой (показываем весь каталог).
  const [debouncedQuery, setDebouncedQuery] = useState(() =>
    filters.query.trim().length >= MIN_QUERY_LEN ? filters.query : "",
  );
  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedQuery(
        filters.query.trim().length >= MIN_QUERY_LEN ? filters.query : "",
      );
    }, 200);
    return () => clearTimeout(id);
  }, [filters.query]);

  const [ownerOpen, setOwnerOpen] = useState(false);
  const [ownerForm, setOwnerForm] = useState<OwnerRequestForm>(initialOwnerRequestForm);
  const [ownerBusy, setOwnerBusy] = useState(false);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [ownerSuccess, setOwnerSuccess] = useState(false);

  const [selectedAddress, setSelectedAddress] = useState<PublicAddress | null>(null);
  const [applicationForm, setApplicationForm] = useState<ClientApplicationForm>(initialClientApplicationForm);
  const [applicationBusy, setApplicationBusy] = useState(false);
  const [applicationError, setApplicationError] = useState<string | null>(null);

  // Per-card user choices: срок (6/11) и подключение корреспонденции.
  // Применяются при клике "Подробнее" → пробрасываются в форму заявки.
  // Выбор срока и корреспонденции по карточкам держим в sessionStorage: раньше
  // это был обычный useState, и переход на 2-ю страницу или F5 сбрасывал уже
  // настроенные цены обратно на 11 мес. без почты.
  const [cardOptions, setCardOptions] = useState<Record<string, CardOptions>>(() =>
    readCardOptions(),
  );
  const getCardOption = (id: string): CardOptions =>
    cardOptions[id] ?? defaultCardOptions;
  const updateCardOption = (id: string, patch: Partial<CardOptions>) =>
    setCardOptions((prev) => {
      const next = { ...prev, [id]: { ...(prev[id] ?? defaultCardOptions), ...patch } };
      writeCardOptions(next);
      return next;
    });

  // Расширенный поиск — модалка с фильтрами (город + ИФНС).
  const [advancedOpen, setAdvancedOpen] = useState(false);
  // Мобильное меню (бургер).
  const [menuOpen, setMenuOpen] = useState(false);
  // Согласия на обработку ПДн: без отметки отправка форм заблокирована.
  const [applicationConsent, setApplicationConsent] = useState(false);
  const [ownerConsent, setOwnerConsent] = useState(false);

  /** Ссылка на документ: настоящий href для новой вкладки, обычный клик — SPA. */
  function openLegalLink(event: React.MouseEvent<HTMLAnchorElement>, doc: LegalDoc) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onOpenLegal(doc);
  }

  // Детальная карточка адреса (фото-галерея + услуги). Что открыто, решает URL:
  // openAddressId приходит сверху, здесь только кешируется сам объект.
  const [detailAddress, setDetailAddress] = useState<PublicAddress | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  // Модалка поиска адресов на карте (Яндекс.Карты).
  const [mapOpen, setMapOpen] = useState(false);
  // Скролл внутри детальной модалки — для кнопки «наверх».
  const detailPanelRef = useRef<HTMLDivElement | null>(null);
  const [detailScrolled, setDetailScrolled] = useState(false);
  const [detailPhotoIdx, setDetailPhotoIdx] = useState(0);

  /** Открыть/закрыть карточку — через URL, чтобы работали «Назад» и ссылка. */
  const openDetail = useCallback(
    (address: PublicAddress | null) => onOpenAddress(address ? address.id : null),
    [onOpenAddress],
  );
  const closeDetail = useCallback(() => onOpenAddress(null), [onOpenAddress]);

  // URL → карточка. Обычно объект уже есть в выдаче; при заходе по прямой
  // ссылке (адреса нет на текущей странице выдачи) догружаем его точечно.
  useEffect(() => {
    if (!openAddressId) {
      setDetailAddress(null);
      setDetailError(null);
      return;
    }
    if (detailAddress?.id === openAddressId) return;

    const fromList = addresses.find((address) => address.id === openAddressId);
    if (fromList) {
      setDetailPhotoIdx(0);
      setDetailError(null);
      setDetailAddress(fromList);
      return;
    }

    let alive = true;
    api
      .publicAddress(openAddressId)
      .then((address) => {
        if (!alive) return;
        setDetailPhotoIdx(0);
        setDetailError(null);
        setDetailAddress(address);
      })
      .catch((err: Error) => {
        if (!alive) return;
        // Адрес сняли с публикации или ссылка битая — не держим пустую модалку.
        setDetailError(err.message);
        onOpenAddress(null);
      });
    return () => {
      alive = false;
    };
  }, [openAddressId, addresses, detailAddress?.id, onOpenAddress]);

  // Чат с собственником: открытый чат + indicator "ожидание входа" +
  // "запомнить адрес для чата на момент логина".
  const [activeChat, setActiveChat] = useState<AddressChat | null>(null);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatAuthPrompt, setChatAuthPrompt] = useState(false);
  // Если клиент кликнул "Задать вопрос" неавторизованным — запоминаем id адреса.
  // sessionStorage переживёт unmount каталога во время логина (AuthView рендерится
  // вместо каталога), а useEffect ниже подберёт его обратно.
  const PENDING_KEY = "ds:pending-chat-address-id";
  const [pendingChatAddressId, setPendingChatAddressIdState] = useState<string | null>(
    () => (typeof window !== "undefined" ? window.sessionStorage.getItem(PENDING_KEY) : null),
  );
  function setPendingChatAddressId(id: string | null) {
    setPendingChatAddressIdState(id);
    if (typeof window === "undefined") return;
    if (id) window.sessionStorage.setItem(PENDING_KEY, id);
    else window.sessionStorage.removeItem(PENDING_KEY);
  }

  async function startChatWithOwner(address: PublicAddress) {
    setChatError(null);
    if (!currentUser) {
      setPendingChatAddressId(address.id);
      setChatAuthPrompt(true);
      return;
    }
    setChatBusy(true);
    try {
      const chat = await api.openChatForAddress(address.id);
      setActiveChat(chat);
      closeDetail();
    } catch (err) {
      setChatError((err as Error).message);
    } finally {
      setChatBusy(false);
    }
  }

  // Авто-открытие чата после логина / регистрации.
  // Сработает один раз: currentUser появился И pendingChatAddressId есть.
  useEffect(() => {
    if (!currentUser || !pendingChatAddressId || activeChat || chatBusy) return;
    let cancelled = false;
    setChatBusy(true);
    api
      .openChatForAddress(pendingChatAddressId)
      .then((chat) => {
        if (cancelled) return;
        setActiveChat(chat);
        closeDetail();
        setChatAuthPrompt(false);
      })
      .catch((err: Error) => {
        if (!cancelled) setChatError(err.message);
      })
      .finally(() => {
        if (!cancelled) {
          setChatBusy(false);
          setPendingChatAddressId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentUser, pendingChatAddressId, activeChat, chatBusy]);

  /** Параметры серверного поиска из текущих фильтров — общие для выдачи и карты. */
  const searchParams = useMemo(
    () => ({
      q: debouncedQuery,
      city: filters.city.trim() || undefined,
      fns_number: filters.fnsNumber ? Number(filters.fnsNumber) : ("" as const),
      region: filters.region || undefined,
      geo_city: filters.geoCity || undefined,
      fns_office_id: filters.fnsOfficeId || undefined,
      correspondence: filters.withCorr || undefined,
      // Диапазон цены из конфигуратора имеет приоритет; чипы filter-бара
      // (budgetUnder30k / premium11) — fallback.
      price_lt: filters.priceTo
        ? Number(filters.priceTo)
        : filters.budgetPreset
          ? BUDGET_PRESET_VALUES[filters.budgetPreset]
          : undefined,
      price_gte: filters.priceFrom
        ? Number(filters.priceFrom)
        : filters.premium11
          ? 25000
          : undefined,
      sort: (filters.sort === "default" ? "relevance" : filters.sort) as
        | "relevance"
        | "price_asc"
        | "price_desc"
        | "newest",
    }),
    [
      debouncedQuery,
      filters.city,
      filters.fnsNumber,
      filters.region,
      filters.geoCity,
      filters.fnsOfficeId,
      filters.withCorr,
      filters.priceFrom,
      filters.priceTo,
      filters.budgetPreset,
      filters.premium11,
      filters.sort,
    ],
  );

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .publicSearchAddresses({
        ...searchParams,
        page,
        page_size: PAGE_SIZE,
      })
      .then((result) => {
        if (!alive) return;
        setAddresses(result.items);
        setTotalCount(result.total);
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
  }, [searchParams, page, reloadKey]);

  // Карта грузит собственную выборку: раньше в неё передавалась текущая
  // страница выдачи (24 адреса), а счётчик «N из 24» это маскировал — на карте
  // молча не было ничего со второй страницы.
  const [mapAddresses, setMapAddresses] = useState<PublicAddress[]>([]);
  const [mapLoading, setMapLoading] = useState(false);
  const [mapTotal, setMapTotal] = useState(0);

  useEffect(() => {
    if (!mapOpen) return;
    let alive = true;
    setMapLoading(true);
    api
      .publicSearchAddresses({ ...searchParams, page: 1, page_size: MAP_MAX_ADDRESSES })
      .then((result) => {
        if (!alive) return;
        setMapAddresses(result.items);
        setMapTotal(result.total);
      })
      .catch(() => {
        if (!alive) return;
        // Карта не критична: пустая выборка честнее, чем чужие метки.
        setMapAddresses([]);
        setMapTotal(0);
      })
      .finally(() => {
        if (alive) setMapLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [mapOpen, searchParams]);

  // При смене любого фильтра кроме page — возвращаемся на 1-ю страницу.
  // (page сам по себе не триггерит этот reset, иначе цикл.)
  // Первый прогон пропускаем: иначе ?page=3 из ссылки тут же схлопывался в 1,
  // и поделиться страницей выдачи было нельзя.
  const filtersSettled = useRef(false);
  useEffect(() => {
    if (!filtersSettled.current) {
      filtersSettled.current = true;
      return;
    }
    setPage(1);
  }, [
    debouncedQuery,
    filters.city,
    filters.fnsNumber,
    filters.region,
    filters.geoCity,
    filters.fnsOfficeId,
    filters.priceFrom,
    filters.priceTo,
    filters.withCorr,
    filters.budgetPreset,
    filters.premium11,
    filters.sort,
  ]);

  // Синк filters + page → query string. replaceState, не push — иначе history
  // засрётся на каждом нажатии в поле поиска. Сохраняем path + hash.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const qs = filtersToQueryString(filters);
    const parts: string[] = [];
    if (qs) parts.push(qs);
    if (page > 1) parts.push(`page=${page}`);
    const newSearch = parts.length ? `?${parts.join("&")}` : "";
    const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    const next = `${window.location.pathname}${newSearch}${window.location.hash}`;
    if (next !== current) {
      // history.state обязательно сохраняем: в нём глубина навигации роутера,
      // по которой кнопка «Назад» понимает, есть ли куда возвращаться.
      window.history.replaceState(window.history.state, "", next);
    }
  }, [filters, page]);

  // Browser back/forward — пересчитать filters + page из URL.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = () => {
      setFilters(filtersFromQueryString(window.location.search));
      const p = new URLSearchParams(window.location.search).get("page");
      setPage(p && /^\d+$/.test(p) ? Math.max(1, parseInt(p, 10)) : 1);
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  // ИФНС-опции грузим один раз — это справочник, при фильтрации не меняется
  // (содержит ИФНС по всем опубликованным адресам, а не по текущей выборке).
  useEffect(() => {
    let alive = true;
    api
      .publicFnsOptions()
      .then((opts) => {
        if (alive) setFnsOptions(opts);
      })
      .catch(() => {
        // Бэк может быть недоступен / older deployment без endpoint'а — silently
        // фолбэк на хардкод MOSCOW_FNS_NUMBERS, см. рендер <select> ниже.
      });
    api
      .publicGeoTree()
      .then((tree) => {
        if (alive) setGeoTree(tree);
      })
      .catch(() => {
        /* гео-дерево недоступно — каскад покажет пустые селекты */
      });
    // Размер каталога: запрос без фильтров, одна запись — нужен только total.
    api
      .publicSearchAddresses({ page: 1, page_size: 1 })
      .then((res) => {
        if (alive) setCatalogTotal(res.total);
      })
      .catch(() => {
        /* счётчик покажет «—», остальная страница не страдает */
      });
    return () => {
      alive = false;
    };
  }, [reloadKey]);

  // Бэк делает всю фильтрацию (FTS + city + ifns + corr + price-bands + sort).
  // Фронт показывает то что пришло. Подсветка совпадений по-прежнему клиентская.
  const filteredAddresses = addresses;

  // Счётчики первого экрана — по справочникам всего каталога, а не по странице
  // выдачи. Оба справочника грузятся один раз и от фильтров не зависят.
  const ifnsCount = useMemo(() => {
    const set = new Set<number>();
    for (const opt of fnsOptions) set.add(opt.fns_number);
    return set.size;
  }, [fnsOptions]);

  // Города считаем по тому же справочнику ИФНС, а не по гео-дереву: дерево
  // строится через fns_office_id, а он у части адресов не проставлен — на проде
  // /marketplace/geo отдаёт пустой список, и счётчик показал бы «—».
  const cityCount = useMemo(() => {
    const set = new Set<string>();
    for (const opt of fnsOptions) {
      if (opt.fns_city) set.add(opt.fns_city);
    }
    return set.size;
  }, [fnsOptions]);

  /** Подсказки для свободного поля «Город» — вынимаются из строк адресов. */
  const cities = useMemo(() => {
    const values = new Set<string>(["Москва"]);
    for (const address of addresses) {
      const match = address.full_address.match(/г\.\s*([^,]+)/i);
      if (match?.[1]) values.add(match[1].trim());
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, "ru"));
  }, [addresses]);

  const hasActiveFilters = Boolean(
    filters.query.trim() ||
      filters.fnsNumber ||
      filters.region ||
      filters.geoCity ||
      filters.fnsOfficeId ||
      filters.priceFrom ||
      filters.priceTo ||
      filters.city !== initialFilters.city ||
      filters.withCorr ||
      filters.budgetPreset ||
      filters.premium11 ||
      filters.sort !== "default",
  );

  // Compare state — выбранные адреса для сравнения.
  // Храним сами объекты, а не только id: список сравнения раньше строился
  // из текущей выдачи, и после смены страницы или фильтра кнопка «Открыть
  // сравнение» оставалась активной, а модалка молча не открывалась.
  const [compared, setCompared] = useState<Map<string, PublicAddress>>(new Map());
  const [compareOpen, setCompareOpen] = useState(false);
  const compareList = useMemo(() => [...compared.values()], [compared]);
  const COMPARE_MAX = 4;
  function toggleCompare(address: PublicAddress) {
    setCompared((prev) => {
      const next = new Map(prev);
      if (next.has(address.id)) next.delete(address.id);
      else if (next.size < COMPARE_MAX) next.set(address.id, address);
      return next;
    });
  }
  function clearCompare() {
    setCompared(new Map());
    setCompareOpen(false);
  }

  function resetFilters() {
    setFilters(initialFilters);
  }

  /**
   * Смена страницы с возвратом к началу выдачи: без этого пользователь
   * оставался внизу и видел хвост уже НОВОЙ страницы — переход выглядел так,
   * будто ничего не произошло.
   */
  function goToPage(next: number) {
    const lastPage = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
    const target = Math.min(Math.max(1, next), lastPage);
    if (target === page) return;
    setPage(target);
    document.getElementById("catalog-grid")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Escape закрывает верхнюю модалку, фон под ней не прокручивается.
  // Правило: Escape делает то же, что клик по фону. Где фон намеренно не
  // закрывает окно (форма заявки), Escape тоже не закрывает — только блокировка
  // прокрутки, иначе случайное нажатие стёрло бы заполненные поля.
  useModalDismiss(!!detailAddress, closeDetail);
  useModalDismiss(!!selectedAddress, null);
  useModalDismiss(advancedOpen, () => setAdvancedOpen(false));
  useModalDismiss(ownerOpen, () => setOwnerOpen(false));
  useModalDismiss(chatAuthPrompt, () => {
    setChatAuthPrompt(false);
    setPendingChatAddressId(null);
  });
  useModalDismiss(!!activeChat, () => setActiveChat(null));
  useModalDismiss(compareOpen, () => setCompareOpen(false));
  // Мобильное меню закрывается по Escape, но фон не блокируем: это выпадающая
  // панель, а не модалка — со страницы под ней уходить нормально.
  useEffect(() => {
    if (!menuOpen) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  async function submitOwnerRequest(event: FormEvent) {
    event.preventDefault();
    setOwnerBusy(true);
    setOwnerError(null);
    setOwnerSuccess(false);
    const payload: ProviderConnectionRequestCreate = {
      company_name: ownerForm.company_name.trim(),
      contact_name: ownerForm.contact_name.trim(),
      contact_email: ownerForm.contact_email.trim(),
      contact_phone: normalizeOptional(ownerForm.contact_phone),
      city: normalizeOptional(ownerForm.city),
      address_count: ownerForm.address_count ? Number(ownerForm.address_count) : null,
      comment: normalizeOptional(ownerForm.comment),
    };
    try {
      await api.createProviderConnectionRequest(payload);
      setOwnerForm(initialOwnerRequestForm);
      setOwnerSuccess(true);
    } catch (err) {
      setOwnerError((err as Error).message);
    } finally {
      setOwnerBusy(false);
    }
  }

  function openApplicationForm(address: PublicAddress) {
    const options = getCardOption(address.id);
    setSelectedAddress(address);
    setApplicationError(null);
    setApplicationForm({
      ...initialClientApplicationForm,
      term_months: options.term,
      has_correspondence_service: options.corr && Boolean(address.correspondence_price),
    });
  }

  async function submitClientApplication(event: FormEvent) {
    event.preventDefault();
    if (!selectedAddress) return;
    setApplicationBusy(true);
    setApplicationError(null);
    const basePayload = {
      address_id: selectedAddress.id,
      contact_name: applicationForm.contact_name.trim(),
      contact_email: applicationForm.contact_email.trim(),
      contact_phone: normalizeOptional(applicationForm.contact_phone),
      password: applicationForm.password,
      term_months: applicationForm.term_months,
      has_correspondence_service: applicationForm.has_correspondence_service,
      contract_city: null,
    };
    const payload: PublicClientApplicationCreate =
      applicationForm.type === "initial_registration"
        ? {
            ...basePayload,
            type: "initial_registration",
            planned_client_name: applicationForm.planned_client_name.trim(),
          }
        : {
            ...basePayload,
            type: "address_change",
            client_inn: applicationForm.client_inn.trim(),
            notice_period: "1m",
            payer_type: applicationForm.payer_type,
          };
    try {
      const result = await api.createPublicApplication(payload);
      setSelectedAddress(null);
      setApplicationForm(initialClientApplicationForm);
      onAuthenticated(result.user);
    } catch (err) {
      setApplicationError((err as Error).message);
    } finally {
      setApplicationBusy(false);
    }
  }

  return (
    <main className="ds-catalog">
      <header className="ds-topnav">
       <div className="ds-topnav__inner">
        {/* href оставлен для «открыть в новой вкладке» и индексации, но обычный
            клик обрабатываем сами — перезагружать всё приложение незачем. */}
        <a
          className="ds-topnav__brand"
          href="/"
          aria-label="uradres.net — на главную"
          onClick={(event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
            event.preventDefault();
            closeDetail();
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          <span className="ds-brandmark" aria-hidden="true">
            <span className="ds-brandmark__pin" />
          </span>
          <span className="ds-brandmark__word">
            uradres<span className="ds-brandmark__tld">.net</span>
          </span>
        </a>
        <nav className="ds-topnav__links" aria-label="Главное меню">
          {MENU_LINKS.map((link) => (
            <a href={link.href} key={link.href}>
              {link.label}
            </a>
          ))}
        </nav>
        {/* Бургер вместо скрытого на мобильном меню: до этого при ширине
            <1024px пункты просто пропадали и попасть в них было нельзя. */}
        <button
          className="ds-topnav__burger"
          type="button"
          aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={menuOpen}
          aria-controls="topnav-mobile"
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <div className="ds-topnav__actions">
          {currentUser && onOpenDashboard ? (
            <button className="ds-btn ds-btn--ghost ds-btn--md" onClick={onOpenDashboard} type="button">
              <KeyRound size={14} />
              Кабинет
            </button>
          ) : (
            <button className="ds-btn ds-btn--ghost ds-btn--md" onClick={onLoginClick} type="button">
              <KeyRound size={14} />
              {canBootstrap ? "Первый вход" : "Войти"}
            </button>
          )}
          <button
            className="ds-btn ds-btn--primary ds-btn--md"
            type="button"
            onClick={() => setAdvancedOpen(true)}
          >
            Подобрать адрес
            <ArrowRight size={14} />
          </button>
        </div>
       </div>

        {menuOpen ? (
          <nav className="ds-topnav__mobile" id="topnav-mobile" aria-label="Меню">
            {MENU_LINKS.map((link) => (
              <a href={link.href} key={link.href} onClick={() => setMenuOpen(false)}>
                {link.label}
              </a>
            ))}
          </nav>
        ) : null}
      </header>

      <motion.section
        id="catalog"
        className="ds-hero"
        initial={reduceMotion ? false : "hidden"}
        animate="visible"
        variants={motionVariants}
      >
        <motion.h1 className="ds-hero__h1" variants={childMotion}>
          Маркетплейс юридических адресов.<br />
          <em>За 1 день.</em>
        </motion.h1>
        <motion.p className="ds-hero__sub" variants={childMotion}>
          Проверенные собственники, готовый комплект документов с гарантийным письмом и выпиской ЕГРН.
          Подходит и для регистрации новой компании, и для смены адреса действующей.
        </motion.p>
        <motion.div className="ds-hero__stats ds-stat-row" variants={childMotion}>
          <div className="ds-stat">
            <div className="ds-stat__num">{catalogTotal || "—"}</div>
            <div className="ds-stat__lbl">{catalogTotal === 1 ? "адрес в каталоге" : "адресов в каталоге"}</div>
          </div>
          <div className="ds-stat">
            <div className="ds-stat__num">{ifnsCount || "—"}</div>
            {/* Было «ИФНС в выборке» — считалось по странице выдачи и врало
                вместе с ней. Теперь это справочник по всему каталогу. */}
            <div className="ds-stat__lbl">ИФНС в каталоге</div>
          </div>
          <div className="ds-stat">
            <div className="ds-stat__num">{cityCount || "—"}</div>
            <div className="ds-stat__lbl">{cityCount === 1 ? "город" : "городов"}</div>
          </div>
          <div className="ds-stat">
            <div className="ds-stat__num">6 и 11</div>
            <div className="ds-stat__lbl">месяцев аренды</div>
          </div>
        </motion.div>

        {/* Декоративная иллюстрация: пустой alt, на узком экране скрыта целиком.
            Стоит последней в разметке, чтобы не вклиниваться между заголовком и
            текстом при чтении с экранного диктора; на месте её держит сетка. */}
        <div aria-hidden="true" className="ds-hero__media">
          <img alt="" decoding="async" fetchPriority="high" src="/hero-office.jpg" />
        </div>
      </motion.section>

      {/*
        Форма подбора на странице. Дизайн-пакет предлагал убрать её и оставить
        только пресеты, но по ней ищут — вернули по просьбе владельца.
        Пресеты ниже остаются как быстрые ярлыки к тем же фильтрам.

        В ряду пресетов только то, что действительно работает. «Готово к
        регистрации» и «Рядом с метро» из макета не выведены: первого нет в
        API (клиентская фильтрация разошлась бы со счётчиком и пагинацией),
        для второго нет данных о станциях ни в модели, ни в выдаче.
      */}
      <HomeConfigurator
        filters={{
          query: filters.query,
          region: filters.region,
          geoCity: filters.geoCity,
          fnsOfficeId: filters.fnsOfficeId,
          priceFrom: filters.priceFrom,
          priceTo: filters.priceTo,
          withCorr: filters.withCorr,
        }}
        onChange={(next) =>
          setFilters({
            ...filters,
            ...next,
            // Ручной ввод «цена до» отменяет пресет: иначе поле показывало бы
            // одно число, а выдача фильтровалась по другому.
            ...(next.priceTo !== undefined && next.priceTo !== filters.priceTo
              ? { budgetPreset: "" as const }
              : {}),
          })
        }
        termMonths={11}
        onTermChange={() => {
          /* MVP: срок выбирается в карточке адреса — там же меняется цена. */
        }}
        geoTree={geoTree}
        totalCount={totalCount}
        loading={loading}
        onShowResults={() => {
          document
            .getElementById("catalog-grid")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
        onReset={resetFilters}
        onOpenMap={() => setMapOpen(true)}
      />

      <div className="ds-quickchips ds-quickchips--standalone">
        <span className="ds-quickchips__label">Подбор</span>
        <button
          aria-pressed={filters.budgetPreset === "lt20"}
          className={filters.budgetPreset === "lt20" ? "ds-chip ds-chip--active" : "ds-chip"}
          onClick={() =>
            setFilters({
              ...filters,
              budgetPreset: filters.budgetPreset === "lt20" ? "" : "lt20",
              // Пресет и поле «цена до» — про одно и то же. Оставлять оба
              // значит показывать активный чип, который ни на что не влияет.
              priceTo: "",
            })
          }
          type="button"
        >
          Дешевле 20 000 ₽
        </button>
        <button
          aria-pressed={filters.budgetPreset === "lt30"}
          className={filters.budgetPreset === "lt30" ? "ds-chip ds-chip--active" : "ds-chip"}
          onClick={() =>
            setFilters({
              ...filters,
              budgetPreset: filters.budgetPreset === "lt30" ? "" : "lt30",
              priceTo: "",
            })
          }
          type="button"
        >
          Дешевле 30 000 ₽
        </button>
        <button
          aria-pressed={filters.withCorr}
          className={filters.withCorr ? "ds-chip ds-chip--active" : "ds-chip"}
          onClick={() => setFilters({ ...filters, withCorr: !filters.withCorr })}
          type="button"
        >
          С почтой
        </button>
        <button
          aria-pressed={filters.sort === "newest"}
          className={filters.sort === "newest" ? "ds-chip ds-chip--active" : "ds-chip"}
          onClick={() =>
            setFilters({ ...filters, sort: filters.sort === "newest" ? "default" : "newest" })
          }
          type="button"
        >
          Сначала новые
        </button>
        <span style={{ flex: 1 }} />
        {hasActiveFilters ? (
          <button className="ds-chip" onClick={resetFilters} type="button">
            Сбросить
          </button>
        ) : null}
        {/* Кнопок «Подобрать адрес» и «На карте» здесь нет: обе есть в форме
            подбора выше и в верхнем меню — третий раз подряд одно и то же. */}
      </div>

      <AddressMapModal
        open={mapOpen}
        addresses={mapAddresses}
        loading={mapLoading}
        totalCount={mapTotal}
        onClose={() => setMapOpen(false)}
        onSelectAddress={(address) => {
          setMapOpen(false);
          setDetailPhotoIdx(0);
          openDetail(address);
        }}
      />

      <div className="ds-resultbar" id="catalog-grid">
        <div>
          {loading ? (
            "Загружаем каталог…"
          ) : (
            <>
              Показано <b>{filteredAddresses.length}</b> из <b>{totalCount}</b> {totalCount === 1 ? "адреса" : "адресов"}
            </>
          )}
        </div>
      </div>

      <div className="ds-gridwrap">
        {loading ? (
          <div className="ds-grid">
            {Array.from({ length: 6 }).map((_, idx) => (
              <div className="ds-skel-card" key={idx}>
                <div className="ds-skel-card__media" />
                <div className="ds-skel-card__body">
                  <div className="ds-skel-line ds-skel-line--lg" />
                  <div className="ds-skel-line" style={{ width: "60%" }} />
                  <div className="ds-skel-line" style={{ width: "40%" }} />
                  <div className="ds-skel-line ds-skel-line--lg" style={{ width: "70%", marginTop: 12 }} />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="ds-emptystate">
            <div className="ds-emptystate__icon ds-emptystate__icon--danger">
              <AlertTriangle size={26} strokeWidth={1.8} />
            </div>
            <h3>Не удалось загрузить каталог</h3>
            <p>Что-то пошло не так на нашей стороне. Попробуйте обновить страницу через минуту — если ошибка повторится, напишите нам.</p>
            <div className="ds-emptystate__actions">
              <button
                className="ds-btn ds-btn--secondary ds-btn--md"
                type="button"
                onClick={() => setOwnerOpen(true)}
              >
                <Mail size={14} />
                Связаться с поддержкой
              </button>
              <button
                className="ds-btn ds-btn--primary ds-btn--md"
                type="button"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                Обновить
              </button>
            </div>
          </div>
        ) : loading ? (
          <div className="ds-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <div className="ds-skel-card" key={index}>
                <div className="ds-skel ds-skel-card__media" />
                <div className="ds-skel-card__body">
                  <div className="ds-skel" style={{ height: 14, width: "70%" }} />
                  <div className="ds-skel" style={{ height: 11, width: "55%" }} />
                  <div className="ds-skel" style={{ height: 18, width: "40%", marginTop: 6 }} />
                </div>
              </div>
            ))}
          </div>
        ) : filteredAddresses.length === 0 ? (
          <div className="ds-emptystate">
            <div className="ds-emptystate__icon">
              <Search size={26} strokeWidth={1.8} />
            </div>
            <h3>
              {hasActiveFilters
                ? "По заданным фильтрам адресов нет"
                : "Опубликованных адресов пока нет"}
            </h3>
            <p>
              {hasActiveFilters
                ? "Сбросьте ненужные фильтры или попробуйте похожую ИФНС:"
                : "Скоро появятся первые адреса от верифицированных собственников."}
            </p>
            {hasActiveFilters && (
              <>
                <div className="ds-emptystate__chips">
                  {filters.query.trim() && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, query: "" })}
                    >
                      Запрос: «{filters.query}» <X size={12} />
                    </button>
                  )}
                  {filters.fnsNumber && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, fnsNumber: "" })}
                    >
                      ИФНС № {filters.fnsNumber} <X size={12} />
                    </button>
                  )}
                  {filters.city !== initialFilters.city && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() =>
                        setFilters({ ...filters, city: initialFilters.city })
                      }
                    >
                      Город: {filters.city || "не указан"} <X size={12} />
                    </button>
                  )}
                  {filters.withCorr && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, withCorr: false })}
                    >
                      С корреспонденцией <X size={12} />
                    </button>
                  )}
                  {filters.budgetPreset && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, budgetPreset: "" })}
                    >
                      До {BUDGET_PRESET_VALUES[filters.budgetPreset].toLocaleString("ru-RU")} ₽{" "}
                      <X size={12} />
                    </button>
                  )}
                  {filters.premium11 && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, premium11: false })}
                    >
                      Премиум от 25 000 ₽ <X size={12} />
                    </button>
                  )}
                  {filters.sort !== "default" && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, sort: "default" })}
                    >
                      Сортировка <X size={12} />
                    </button>
                  )}
                  {/* Фильтры конфигуратора (регион / город / ИФНС-офис / цена)
                      сюда не попадали: экран советовал «сбрось ненужные
                      фильтры», а сбрасывать было нечего — блок чипов оставался
                      пустым, хотя выдача была отфильтрована. */}
                  {filters.region && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() =>
                        setFilters({ ...filters, region: "", geoCity: "", fnsOfficeId: "" })
                      }
                    >
                      Регион: {filters.region} <X size={12} />
                    </button>
                  )}
                  {filters.geoCity && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, geoCity: "", fnsOfficeId: "" })}
                    >
                      Город: {filters.geoCity} <X size={12} />
                    </button>
                  )}
                  {filters.fnsOfficeId && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, fnsOfficeId: "" })}
                    >
                      Выбранная ИФНС <X size={12} />
                    </button>
                  )}
                  {filters.priceFrom && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, priceFrom: "" })}
                    >
                      Цена от {Number(filters.priceFrom).toLocaleString("ru-RU")} ₽{" "}
                      <X size={12} />
                    </button>
                  )}
                  {filters.priceTo && (
                    <button
                      type="button"
                      className="ds-chip ds-chip--active"
                      onClick={() => setFilters({ ...filters, priceTo: "" })}
                    >
                      Цена до {Number(filters.priceTo).toLocaleString("ru-RU")} ₽{" "}
                      <X size={12} />
                    </button>
                  )}
                  <button
                    type="button"
                    className="ds-chip"
                    onClick={resetFilters}
                  >
                    Сбросить все
                  </button>
                </div>

                {/* Похожие ИФНС: если есть текущий фильтр по ИФНС — top-3 других
                    с самым большим количеством адресов. */}
                {filters.fnsNumber &&
                  fnsOptions.filter(
                    (o) => String(o.fns_number) !== filters.fnsNumber,
                  ).length > 0 && (
                    <div className="ds-emptystate__suggest">
                      <span className="ds-emptystate__suggest-label">
                        Похожие ИФНС с адресами:
                      </span>
                      <div className="ds-emptystate__chips">
                        {fnsOptions
                          .filter((o) => String(o.fns_number) !== filters.fnsNumber)
                          .slice(0, 3)
                          .map((opt) => (
                            <button
                              key={opt.fns_number}
                              type="button"
                              className="ds-chip"
                              onClick={() =>
                                setFilters({
                                  ...filters,
                                  fnsNumber: String(opt.fns_number),
                                })
                              }
                            >
                              ИФНС № {opt.fns_number} · {opt.count}
                              {opt.count === 1 ? " адрес" : " адр."}
                            </button>
                          ))}
                      </div>
                    </div>
                  )}

                <div className="ds-emptystate__actions">
                  <button
                    className="ds-btn ds-btn--primary ds-btn--md"
                    type="button"
                    onClick={resetFilters}
                  >
                    Сбросить все
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <motion.div
            className="ds-grid"
            initial={reduceMotion ? false : "hidden"}
            animate="visible"
            variants={gridMotion}
            key={`${filters.city}-${filteredAddresses.length}`}
          >
            {filteredAddresses.map((address) => {
              const initials = streetInitials(address.full_address);
              const fresh = isRecent(address.created_at);
              const options = getCardOption(address.id);
              const base = options.term === 6 ? address.price_6m : address.price_11m;
              const total =
                options.corr && address.correspondence_price
                  ? Number(base) +
                    Number(address.correspondence_price) * options.term
                  : base;
              const hasCorr = address.correspondence_price !== null && address.correspondence_price !== undefined;
              return (
                <motion.div
                  className={`ds-card${compared.has(address.id) ? " ds-card--compared" : ""}`}
                  variants={cardMotion}
                  key={address.id}
                >
                  <label
                    className={`ds-card__compare${compared.has(address.id) ? " selected" : ""}`}
                    title="Добавить к сравнению"
                  >
                    <input
                      type="checkbox"
                      checked={compared.has(address.id)}
                      onChange={() => toggleCompare(address)}
                      disabled={
                        !compared.has(address.id) && compared.size >= COMPARE_MAX
                      }
                    />
                    <span>Сравнить</span>
                  </label>
                  <button
                    type="button"
                    className="ds-card__media ds-card__media--clickable"
                    onClick={() => {
                      setDetailPhotoIdx(0);
                      openDetail(address);
                    }}
                    aria-label={`Открыть карточку: ${address.full_address}`}
                  >
                    {fresh && (
                      <span className="ds-card__media-overlay ds-badge ds-badge--new">
                        <span className="ds-badge__dot" />
                        Новый адрес
                      </span>
                    )}
                    <div className="ds-card__media-fallback">
                      <div>
                        <div className="ds-card__media-fallback-initials">{initials}</div>
                        <div className="ds-card__media-fallback-meta">
                          {address.fns_number ? `ИФНС № ${address.fns_number}` : "ИФНС не указана"}
                        </div>
                      </div>
                    </div>
                    {address.main_photo_url && (
                      <img
                        className="ds-card__media-img"
                        src={address.main_photo_url}
                        alt=""
                        loading="lazy"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = "none";
                        }}
                      />
                    )}
                    {address.photos.length > 1 && (
                      <span className="ds-card__media-count">
                        +{address.photos.length - 1} фото
                      </span>
                    )}
                    <span className="ds-card__media-hint">Подробнее →</span>
                  </button>
                  <div className="ds-card__body">
                    <h3 className="ds-card__title">
                      <HighlightMatch text={address.full_address} query={filters.query} />
                    </h3>
                    <div className="ds-card__sub">
                      {address.room_number ? `${address.room_number} · ` : ""}
                      {address.fns_number ? (
                        <HighlightMatch
                          text={`ИФНС № ${address.fns_number}`}
                          query={filters.query}
                        />
                      ) : (
                        ""
                      )}
                    </div>
                    {address.rating_count > 0 && (
                      <div className="ds-card__rating">
                        <StarRating
                          value={address.rating_avg}
                          count={address.rating_count}
                          size={13}
                        />
                      </div>
                    )}
                    <div className="ds-card__options">
                      <div className="ds-segmented" role="group" aria-label="Срок">
                        <button
                          type="button"
                          className={options.term === 11 ? "selected" : ""}
                          onClick={() => updateCardOption(address.id, { term: 11 })}
                        >
                          11 мес.
                        </button>
                        <button
                          type="button"
                          className={options.term === 6 ? "selected" : ""}
                          onClick={() => updateCardOption(address.id, { term: 6 })}
                        >
                          6 мес.
                        </button>
                      </div>
                      {hasCorr && (
                        <label className="ds-corr-toggle">
                          <input
                            type="checkbox"
                            checked={options.corr}
                            onChange={(event) =>
                              updateCardOption(address.id, { corr: event.target.checked })
                            }
                          />
                          <span>
                            + почта {formatMoney(address.correspondence_price)}/мес
                          </span>
                        </label>
                      )}
                    </div>
                    <div className="ds-card__row">
                      <div className="ds-card__price-block">
                        <div className="ds-card__price">{formatMoney(total)}</div>
                        <div className="ds-card__price-term">за {options.term} мес.</div>
                      </div>
                      <button
                        type="button"
                        className="ds-btn ds-btn--primary ds-btn--sm"
                        onClick={() => openApplicationForm(address)}
                      >
                        Оформить заявку
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        )}

        {/* Пагинация. Прячем если total ≤ page_size (одна страница). */}
        {!loading && totalCount > PAGE_SIZE && (
          <nav className="ds-pagination" aria-label="Постраничная навигация">
            <button
              type="button"
              className="ds-btn ds-btn--ghost ds-btn--sm"
              onClick={() => goToPage(page - 1)}
              disabled={page <= 1}
            >
              ← Назад
            </button>
            <span className="ds-pagination__info">
              Страница <b>{page}</b> из <b>{Math.ceil(totalCount / PAGE_SIZE)}</b>
            </span>
            <button
              type="button"
              className="ds-btn ds-btn--ghost ds-btn--sm"
              onClick={() => goToPage(page + 1)}
              disabled={page >= Math.ceil(totalCount / PAGE_SIZE)}
            >
              Вперёд →
            </button>
          </nav>
        )}
      </div>

      <HomeSteps />
      <HomeForOwners onCTAClick={() => setOwnerOpen(true)} />
      <HomeCases />
      <HomeFAQ />

      <footer className="ds-footer">
        <div className="ds-footer__inner">
          <span className="ds-footer__brand">uradres.net</span>
          <nav className="ds-footer__links" aria-label="Правовая информация">
            <button type="button" onClick={() => onOpenLegal("privacy")}>
              Политика обработки персональных данных
            </button>
            <button type="button" onClick={() => onOpenLegal("consent")}>
              Согласие на обработку данных
            </button>
            <button type="button" onClick={() => onOpenLegal("offer")}>
              Публичная оферта
            </button>
          </nav>
          <p className="ds-footer__note">
            Отправляя формы на сайте, вы соглашаетесь с обработкой персональных данных.
            Сервис не является регистрирующим органом; решение о регистрации принимает ФНС.
          </p>
        </div>
      </footer>

      {selectedAddress && (
        <div className="modal-backdrop modal-backdrop--top">
          <form className="modal-panel public-application-modal" onSubmit={submitClientApplication}>
            <header>
              <div>
                <span className="eyebrow">Заявка клиента</span>
                <h2>Подать заявку на адрес</h2>
              </div>
              <button className="text-action" onClick={() => setSelectedAddress(null)} type="button">
                <X size={16} /> Закрыть
              </button>
            </header>

            <div className="selected-address-strip">
              <MapPin size={18} />
              <div>
                <strong>{selectedAddress.full_address}</strong>
                <span>
                  {selectedAddress.provider_name} · ИФНС {selectedAddress.fns_number || "не указана"} ·{" "}
                  {formatMoney(applicationForm.term_months === 6 ? selectedAddress.price_6m : selectedAddress.price_11m)}
                </span>
              </div>
            </div>

            <div className="segmented">
              <button
                className={applicationForm.type === "initial_registration" ? "selected" : ""}
                onClick={() => setApplicationForm({ ...applicationForm, type: "initial_registration" })}
                type="button"
              >
                Первичная регистрация
              </button>
              <button
                className={applicationForm.type === "address_change" ? "selected" : ""}
                onClick={() => setApplicationForm({ ...applicationForm, type: "address_change" })}
                type="button"
              >
                Смена адреса
              </button>
            </div>

            {applicationForm.type === "initial_registration" ? (
              <label className="field">
                <span>Название будущей компании</span>
                <input
                  value={applicationForm.planned_client_name}
                  onChange={(event) => setApplicationForm({ ...applicationForm, planned_client_name: event.target.value })}
                  required
                />
              </label>
            ) : (
              <>
                <label className="field">
                  <span>ИНН компании</span>
                  <input
                    inputMode="numeric"
                    maxLength={10}
                    value={applicationForm.client_inn}
                    onChange={(event) => setApplicationForm({ ...applicationForm, client_inn: event.target.value })}
                    required
                  />
                </label>
                <label className="field">
                  <span>Способ оплаты</span>
                  <div className="segmented public-segmented">
                    <button
                      className={applicationForm.payer_type === "individual" ? "selected" : ""}
                      onClick={() => setApplicationForm({ ...applicationForm, payer_type: "individual" })}
                      type="button"
                    >
                      Я плачу как физлицо (СБП)
                    </button>
                    <button
                      className={applicationForm.payer_type === "juridical" ? "selected" : ""}
                      onClick={() => setApplicationForm({ ...applicationForm, payer_type: "juridical" })}
                      type="button"
                    >
                      Счёт на юр.лицо
                    </button>
                  </div>
                </label>
              </>
            )}

            <div className="client-application-grid">
              <label className="field">
                <span>Контактное лицо</span>
                <input
                  value={applicationForm.contact_name}
                  onChange={(event) => setApplicationForm({ ...applicationForm, contact_name: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>E-mail для аккаунта</span>
                <input
                  inputMode="email"
                  value={applicationForm.contact_email}
                  onChange={(event) => setApplicationForm({ ...applicationForm, contact_email: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Телефон</span>
                <PhoneInput
                  value={applicationForm.contact_phone}
                  onChange={(value) => setApplicationForm({ ...applicationForm, contact_phone: value })}
                />
              </label>
              <label className="field">
                <span>Пароль</span>
                <input
                  minLength={8}
                  value={applicationForm.password}
                  onChange={(event) => setApplicationForm({ ...applicationForm, password: event.target.value })}
                  required
                  type="password"
                />
              </label>
            </div>

            <div className="client-application-options">
              <label className="field">
                <span>Срок</span>
                <div className="segmented public-segmented">
                  <button
                    className={applicationForm.term_months === 11 ? "selected" : ""}
                    onClick={() => setApplicationForm({ ...applicationForm, term_months: 11 })}
                    type="button"
                  >
                    11 мес.
                  </button>
                  <button
                    className={applicationForm.term_months === 6 ? "selected" : ""}
                    onClick={() => setApplicationForm({ ...applicationForm, term_months: 6 })}
                    type="button"
                  >
                    6 мес.
                  </button>
                </div>
              </label>
              <label className="toggle-field compact catalog-toggle">
                <input
                  checked={applicationForm.has_correspondence_service}
                  disabled={!selectedAddress.correspondence_price}
                  onChange={(event) =>
                    setApplicationForm({ ...applicationForm, has_correspondence_service: event.target.checked })
                  }
                  type="checkbox"
                />
                <span>Корреспонденция</span>
              </label>
            </div>

            {applicationError ? <div className="inline-error compact-error">{applicationError}</div> : null}

            <label className="ds-consent">
              <input
                type="checkbox"
                checked={applicationConsent}
                onChange={(event) => setApplicationConsent(event.target.checked)}
                required
              />
              <span>
                Я даю{" "}
                <a href="/legal/consent" onClick={(e) => openLegalLink(e, "consent")}>
                  согласие на обработку персональных данных
                </a>{" "}
                и принимаю{" "}
                <a href="/legal/offer" onClick={(e) => openLegalLink(e, "offer")}>
                  условия оферты
                </a>
                .
              </span>
            </label>

            <div className="actions">
              <button
                className="ds-btn ds-btn--primary ds-btn--lg"
                disabled={applicationBusy || !applicationConsent}
                type="submit"
              >
                {applicationBusy ? <Loader2 className="spin" size={16} /> : <FileText size={16} />}
                Создать заявку и аккаунт
              </button>
            </div>
          </form>
        </div>
      )}

      {detailAddress && (
        <div className="modal-backdrop" onClick={closeDetail}>
          <div
            className="modal-panel ds-address-detail"
            ref={detailPanelRef}
            onClick={(e) => e.stopPropagation()}
            onScroll={(e) => setDetailScrolled(e.currentTarget.scrollTop > 300)}
          >
            <header>
              <div>
                <span className="eyebrow">Адрес</span>
                <h2>{detailAddress.full_address}</h2>
              </div>
              <button className="text-action" onClick={closeDetail} type="button">
                <X size={16} /> Закрыть
              </button>
            </header>

            <div className="ds-address-detail__body">
              <div className="ds-address-detail__gallery">
                <div className="ds-address-detail__photo">
                  <div className="ds-address-detail__photo-fallback">
                    <div className="ds-card__media-fallback-initials">
                      {streetInitials(detailAddress.full_address)}
                    </div>
                    <div className="ds-card__media-fallback-meta">
                      {detailAddress.fns_number
                        ? `ИФНС № ${detailAddress.fns_number}`
                        : "ИФНС не указана"}
                    </div>
                  </div>
                  {detailAddress.photos.length > 0 && (
                    <img
                      src={detailAddress.photos[detailPhotoIdx]?.url}
                      alt=""
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = "none";
                      }}
                    />
                  )}
                  {detailAddress.photos.length > 1 && (
                    <>
                      <button
                        type="button"
                        className="ds-address-detail__nav ds-address-detail__nav--prev"
                        onClick={() =>
                          setDetailPhotoIdx(
                            (idx) =>
                              (idx - 1 + detailAddress.photos.length) %
                              detailAddress.photos.length,
                          )
                        }
                        aria-label="Предыдущее фото"
                      >
                        ‹
                      </button>
                      <button
                        type="button"
                        className="ds-address-detail__nav ds-address-detail__nav--next"
                        onClick={() =>
                          setDetailPhotoIdx(
                            (idx) => (idx + 1) % detailAddress.photos.length,
                          )
                        }
                        aria-label="Следующее фото"
                      >
                        ›
                      </button>
                    </>
                  )}
                </div>
                {detailAddress.photos.length > 1 && (
                  <div className="ds-address-detail__thumbs">
                    {detailAddress.photos.map((photo, idx) => (
                      <button
                        type="button"
                        key={photo.id}
                        className={`ds-address-detail__thumb${
                          idx === detailPhotoIdx ? " selected" : ""
                        }`}
                        onClick={() => setDetailPhotoIdx(idx)}
                      >
                        <img src={photo.url} alt="" />
                      </button>
                    ))}
                  </div>
                )}
                {detailAddress.description && (
                  <p className="ds-address-detail__description">
                    {detailAddress.description}
                  </p>
                )}
              </div>

              <aside className="ds-address-detail__info">
                <div className="ds-address-detail__meta">
                  <div>
                    <span className="ds-address-detail__lbl">Собственник</span>
                    <span className="ds-address-detail__val">
                      {detailAddress.provider_name}
                    </span>
                  </div>
                  <div>
                    <span className="ds-address-detail__lbl">ИФНС</span>
                    <span className="ds-address-detail__val">
                      {detailAddress.fns_number
                        ? `№ ${detailAddress.fns_number}${
                            detailAddress.fns_city ? ` по ${detailAddress.fns_city}` : ""
                          }`
                        : "не указана"}
                    </span>
                  </div>
                  {detailAddress.room_number && (
                    <div>
                      <span className="ds-address-detail__lbl">Помещение</span>
                      <span className="ds-address-detail__val">
                        {detailAddress.room_number}
                      </span>
                    </div>
                  )}
                </div>

                <div className="ds-address-detail__prices">
                  <div className="ds-address-detail__price-row">
                    <span>11 месяцев</span>
                    <strong>{formatMoney(detailAddress.price_11m)}</strong>
                  </div>
                  <div className="ds-address-detail__price-row">
                    <span>6 месяцев</span>
                    <strong>{formatMoney(detailAddress.price_6m)}</strong>
                  </div>
                  {detailAddress.correspondence_price && (
                    <div className="ds-address-detail__price-row ds-address-detail__price-row--soft">
                      <span>Почта</span>
                      <strong>{formatMoney(detailAddress.correspondence_price)}/мес</strong>
                    </div>
                  )}
                </div>

                {detailAddress.services.length > 0 && (() => {
                  const docs = detailAddress.services.filter((s) =>
                    SERVICE_DOCUMENTS.has(s.kind),
                  );
                  const extras = detailAddress.services.filter(
                    (s) => !SERVICE_DOCUMENTS.has(s.kind),
                  );
                  return (
                    <div className="ds-address-detail__services">
                      {docs.length > 0 && (
                        <>
                          <h3>Входит в стоимость</h3>
                          <ul className="ds-address-detail__services--included">
                            {docs.map((svc) => (
                              <li key={svc.id}>
                                <span>{serviceLabel(svc.kind)}</span>
                                <CheckCircle2
                                  size={18}
                                  strokeWidth={2.2}
                                  className="ds-address-detail__check"
                                  aria-label="включено"
                                />
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                      {extras.length > 0 && (
                        <>
                          <h3 style={{ marginTop: docs.length > 0 ? 12 : 0 }}>
                            Дополнительные услуги
                          </h3>
                          <ul className="ds-address-detail__services--extras">
                            {extras.map((svc) => (
                              <li key={svc.id}>
                                <span>{serviceLabel(svc.kind)}</span>
                                <strong>{formatMoney(svc.price)}</strong>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                      <p className="ds-address-detail__services-hint">
                        Подключаются после оформления заявки.
                      </p>
                    </div>
                  );
                })()}

                <div className="ds-address-detail__ctas">
                  <button
                    type="button"
                    className="ds-btn ds-btn--primary ds-btn--md ds-address-detail__cta"
                    onClick={() => openApplicationForm(detailAddress)}
                  >
                    Оформить заявку
                    <ChevronRight size={16} />
                  </button>
                  <button
                    type="button"
                    className="ds-btn ds-btn--secondary ds-btn--md ds-address-detail__cta"
                    disabled={chatBusy}
                    onClick={() => startChatWithOwner(detailAddress)}
                  >
                    {chatBusy ? "Открываем…" : "Задать вопрос"}
                  </button>
                  {chatError && (
                    <div className="ds-input-error-text" style={{ marginTop: 4 }}>
                      {chatError}
                    </div>
                  )}
                </div>
              </aside>
            </div>

            <AddressReviews
              addressId={detailAddress.id}
              canReview={currentUser?.role === "client"}
            />

            {detailScrolled && (
              <button
                type="button"
                className="ds-detail-totop"
                aria-label="Наверх"
                onClick={() =>
                  detailPanelRef.current?.scrollTo({ top: 0, behavior: "smooth" })
                }
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </div>
      )}

      {advancedOpen && (
        <div className="modal-backdrop" onClick={() => setAdvancedOpen(false)}>
          <div
            className="modal-panel public-application-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <span className="eyebrow">Подбор адреса</span>
                <h2>Расширенный поиск</h2>
              </div>
              <button className="text-action" onClick={() => setAdvancedOpen(false)} type="button">
                <X size={16} /> Закрыть
              </button>
            </header>
            <p style={{ fontSize: 13, color: "var(--ds-slate-500)", marginTop: 0 }}>
              Срок и подключение корреспонденции выбираются прямо в карточке адреса —
              цена обновится автоматически.
            </p>
            <div className="form-grid">
              <label className="field">
                <span>Город</span>
                <input
                  list="ds-public-cities-modal"
                  value={filters.city}
                  onChange={(event) => setFilters({ ...filters, city: event.target.value })}
                  placeholder="Москва"
                />
                <datalist id="ds-public-cities-modal">
                  {cities.map((city) => (
                    <option key={city} value={city} />
                  ))}
                </datalist>
              </label>
              <label className="field">
                <span>ИФНС</span>
                <select
                  value={filters.fnsNumber}
                  onChange={(event) => setFilters({ ...filters, fnsNumber: event.target.value })}
                >
                  <option value="">Все ИФНС</option>
                  {fnsOptions.length > 0
                    ? fnsOptions.map((opt) => (
                        <option key={opt.fns_number} value={opt.fns_number}>
                          ИФНС № {opt.fns_number} · {opt.count}
                          {opt.count === 1 ? " адрес" : " адр."}
                        </option>
                      ))
                    : MOSCOW_FNS_NUMBERS.map((num) => (
                        <option key={num} value={num}>
                          ИФНС № {num}
                        </option>
                      ))}
                </select>
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>Поиск по адресу или номеру ИФНС</span>
                <input
                  value={filters.query}
                  onChange={(event) => setFilters({ ...filters, query: event.target.value })}
                  placeholder="часть адреса, например «Тверская»"
                />
              </label>
            </div>

            <div
              className="row-actions"
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              {hasActiveFilters && (
                <button
                  type="button"
                  className="ds-btn ds-btn--ghost ds-btn--md"
                  onClick={resetFilters}
                >
                  Сбросить
                </button>
              )}
              <button
                type="button"
                className="ds-btn ds-btn--primary ds-btn--md"
                onClick={() => {
                  setAdvancedOpen(false);
                  const grid = document.getElementById("catalog-grid");
                  grid?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
              >
                Применить
              </button>
            </div>
          </div>
        </div>
      )}

      {ownerOpen && (
        <div className="modal-backdrop" onClick={() => setOwnerOpen(false)}>
          <form className="modal-panel public-application-modal" onSubmit={submitOwnerRequest} onClick={(e) => e.stopPropagation()}>
            <header>
              <div>
                <span className="eyebrow">Для собственников</span>
                <h2>Подключить адреса в каталог</h2>
              </div>
              <button className="text-action" onClick={() => setOwnerOpen(false)} type="button">
                <X size={16} /> Закрыть
              </button>
            </header>
            <p style={{ fontSize: 13, color: "var(--ds-slate-500)", marginTop: 0 }}>
              <Sparkles size={14} style={{ verticalAlign: "-2px" }} /> Расскажите о компании и адресах — мы свяжемся в течение рабочего дня и пришлём приглашение в админку.
            </p>

            <label className="field">
              <span>Компания</span>
              <input
                value={ownerForm.company_name}
                onChange={(event) => setOwnerForm({ ...ownerForm, company_name: event.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>Контактное лицо</span>
              <input
                value={ownerForm.contact_name}
                onChange={(event) => setOwnerForm({ ...ownerForm, contact_name: event.target.value })}
                required
              />
            </label>
            <div className="client-application-grid">
              <label className="field">
                <span>E-mail</span>
                <input
                  type="email"
                  value={ownerForm.contact_email}
                  onChange={(event) => setOwnerForm({ ...ownerForm, contact_email: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Телефон</span>
                <PhoneInput
                  value={ownerForm.contact_phone}
                  onChange={(value) => setOwnerForm({ ...ownerForm, contact_phone: value })}
                />
              </label>
              <label className="field">
                <span>Город</span>
                <input
                  value={ownerForm.city}
                  onChange={(event) => setOwnerForm({ ...ownerForm, city: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Адресов</span>
                <input
                  type="number"
                  min={0}
                  value={ownerForm.address_count}
                  onChange={(event) => setOwnerForm({ ...ownerForm, address_count: event.target.value })}
                />
              </label>
            </div>
            <label className="field">
              <span>Комментарий</span>
              <textarea
                value={ownerForm.comment}
                onChange={(event) => setOwnerForm({ ...ownerForm, comment: event.target.value })}
                rows={4}
              />
            </label>

            {ownerError ? <div className="inline-error compact-error">{ownerError}</div> : null}
            {ownerSuccess ? (
              <div className="success-note">
                <CheckCircle2 size={16} />
                Заявка отправлена. Проверьте почту — мы напишем в течение рабочего дня.
              </div>
            ) : null}

            <label className="ds-consent">
              <input
                type="checkbox"
                checked={ownerConsent}
                onChange={(event) => setOwnerConsent(event.target.checked)}
                required
              />
              <span>
                Я даю{" "}
                <a href="/legal/consent" onClick={(e) => openLegalLink(e, "consent")}>
                  согласие на обработку персональных данных
                </a>
                .
              </span>
            </label>

            <div className="actions">
              <button
                className="ds-btn ds-btn--primary ds-btn--lg"
                disabled={ownerBusy || !ownerConsent}
                type="submit"
              >
                {ownerBusy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                Отправить заявку
              </button>
            </div>
          </form>
        </div>
      )}

      {chatAuthPrompt && (
        <div
          className="modal-backdrop"
          onClick={() => {
            setChatAuthPrompt(false);
            setPendingChatAddressId(null);
          }}
        >
          <div className="modal-panel" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <header>
              <div>
                <span className="eyebrow">Регистрация</span>
                <h2>Чтобы написать собственнику — войдите</h2>
              </div>
              <button
                className="text-action"
                type="button"
                onClick={() => {
                  setChatAuthPrompt(false);
                  setPendingChatAddressId(null);
                }}
              >
                <X size={16} /> Закрыть
              </button>
            </header>
            <p style={{ margin: 0, color: "var(--ds-slate-600)", fontSize: 14, lineHeight: 1.5 }}>
              Чат становится доступен после регистрации. Вы можете оформить заявку на адрес —
              аккаунт создастся автоматически вместе с заявкой. Либо войдите в существующий аккаунт.
            </p>
            <div className="row-actions" style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
              <button
                type="button"
                className="ds-btn ds-btn--ghost ds-btn--sm"
                onClick={() => {
                  setChatAuthPrompt(false);
                  onLoginClick();
                }}
              >
                Войти
              </button>
              {detailAddress && (
                <button
                  type="button"
                  className="ds-btn ds-btn--primary ds-btn--sm"
                  onClick={() => {
                    setChatAuthPrompt(false);
                    openApplicationForm(detailAddress);
                  }}
                >
                  Оформить заявку
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {activeChat && currentUser && (
        <div className="modal-backdrop" onClick={() => setActiveChat(null)}>
          <div
            className="modal-panel"
            style={{ maxWidth: 640, width: "100%", padding: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            <AddressChatPanel
              chat={activeChat}
              currentUser={currentUser}
              onClose={() => setActiveChat(null)}
            />
          </div>
        </div>
      )}

      {compared.size > 0 && (
        <div className="ds-compare-bar">
          <div className="ds-compare-bar__count">
            <strong>{compared.size}</strong> / {COMPARE_MAX} к сравнению
          </div>
          <button
            type="button"
            className="ds-btn ds-btn--primary ds-btn--sm"
            onClick={() => setCompareOpen(true)}
            disabled={compared.size < 2}
          >
            Открыть сравнение
          </button>
          <button
            type="button"
            className="ds-btn ds-btn--ghost ds-btn--sm"
            onClick={clearCompare}
          >
            Сбросить
          </button>
        </div>
      )}

      {compareOpen && compareList.length >= 2 && (
        <div className="modal-backdrop" onClick={() => setCompareOpen(false)}>
          <div
            className="modal-panel ds-compare-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <span className="eyebrow">Сравнение</span>
                <h2>{compareList.length} адреса бок-о-бок</h2>
              </div>
              <button className="text-action" type="button" onClick={() => setCompareOpen(false)}>
                <X size={16} /> Закрыть
              </button>
            </header>
            <div className="ds-compare-table" style={{ gridTemplateColumns: `170px repeat(${compareList.length}, minmax(180px, 1fr))` }}>
              <div className="ds-compare-table__rowlbl" />
              {compareList.map((a) => (
                <div key={`hdr-${a.id}`} className="ds-compare-table__hdr">
                  <div className="ds-compare-table__photo">
                    {a.main_photo_url ? (
                      <img src={a.main_photo_url} alt="" />
                    ) : (
                      <span>{streetInitials(a.full_address)}</span>
                    )}
                  </div>
                  <strong>{a.full_address}</strong>
                  <span>{a.provider_name}</span>
                </div>
              ))}

              <div className="ds-compare-table__rowlbl">ИФНС</div>
              {compareList.map((a) => (
                <div key={`fns-${a.id}`} className="ds-compare-table__cell">
                  {a.fns_number ? `№ ${a.fns_number}` : "—"}
                </div>
              ))}

              <div className="ds-compare-table__rowlbl">Цена 6 мес</div>
              {compareList.map((a) => (
                <div key={`p6-${a.id}`} className="ds-compare-table__cell">{formatMoney(a.price_6m)}</div>
              ))}

              <div className="ds-compare-table__rowlbl">Цена 11 мес</div>
              {compareList.map((a) => (
                <div key={`p11-${a.id}`} className="ds-compare-table__cell">
                  <strong>{formatMoney(a.price_11m)}</strong>
                </div>
              ))}

              <div className="ds-compare-table__rowlbl">Корреспонденция</div>
              {compareList.map((a) => (
                <div key={`corr-${a.id}`} className="ds-compare-table__cell">
                  {a.correspondence_price != null ? formatMoney(a.correspondence_price) : "—"}
                </div>
              ))}

              <div className="ds-compare-table__rowlbl">Фото</div>
              {compareList.map((a) => (
                <div key={`ph-${a.id}`} className="ds-compare-table__cell">
                  {a.photos.length} шт.
                </div>
              ))}

              <div className="ds-compare-table__rowlbl">Доп.услуги</div>
              {compareList.map((a) => (
                <div key={`sv-${a.id}`} className="ds-compare-table__cell ds-compare-table__cell--mini">
                  {a.services.length === 0
                    ? "—"
                    : a.services.map((s) => (
                        <div key={s.id}>
                          {serviceLabel(s.kind)} — {formatMoney(s.price)}
                        </div>
                      ))}
                </div>
              ))}

              <div className="ds-compare-table__rowlbl" />
              {compareList.map((a) => (
                <div key={`cta-${a.id}`} className="ds-compare-table__cell">
                  <button
                    type="button"
                    className="ds-btn ds-btn--primary ds-btn--sm"
                    onClick={() => {
                      setCompareOpen(false);
                      openApplicationForm(a);
                    }}
                  >
                    Оформить
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

// Сохраняем именованный экспорт неиспользуемых иконок чтобы tree-shake не выкинул нужные.
// (Building2/Camera импортированы для будущих фаз.)
export const _DS_ICONS_PROBE = { Building2, Camera };
