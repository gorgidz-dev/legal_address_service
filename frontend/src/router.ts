/**
 * Минимальный роутер поверх History API — без зависимостей.
 *
 * Почему не react-router: приложение построено на переключении экранов через
 * useState, полная миграция задела бы каждый компонент. Здесь ровно тот минимум,
 * которого не хватало: адрес в строке браузера ↔ экран, рабочие «Назад»/«Вперёд»
 * и восстановление того же экрана после F5.
 *
 * nginx отдаёт index.html на любой путь (try_files $uri $uri/ /index.html),
 * поэтому прямой заход на /app/registry работает.
 */
import { useCallback, useEffect, useState } from "react";

/** Правовые документы сервиса. Значение = сегмент пути. */
export const LEGAL_DOCS = ["privacy", "offer", "consent"] as const;
export type LegalDoc = (typeof LEGAL_DOCS)[number];

export type Route =
  /** Публичный лендинг + каталог. Главная для всех, включая залогиненных. */
  | { name: "home" }
  /** Карточка адреса из каталога — шарится ссылкой. */
  | { name: "address"; id: string }
  /** Правовые документы: /legal/privacy, /legal/offer, /legal/consent. */
  | { name: "legal"; doc: LegalDoc }
  /** Экран входа. next — куда вернуть после успешной авторизации. */
  | { name: "login"; next: string }
  /** Приём приглашения по токену из письма. */
  | { name: "invite"; token: string }
  /**
   * Кабинет (админ/клиент/собственник): section — раздел, id — выбранная
   * карточка внутри раздела (заявка), чтобы F5 не сбрасывал выбор.
   */
  | { name: "cabinet"; section: string | null; id: string | null };

/** Ключ, под которым в history.state лежит глубина навигации внутри приложения. */
const DEPTH_KEY = "uradresDepth";

/**
 * Защита от open redirect: `next` приходит из строки браузера, поэтому пускаем
 * только относительные пути. `//evil.com` браузер трактует как протокол-
 * относительный абсолютный URL — его тоже отсекаем.
 */
function isSafeInternalPath(path: string): boolean {
  return path.startsWith("/") && !path.startsWith("//");
}

export function parseRoute(pathname: string, search = ""): Route {
  const segments = pathname.split("/").filter(Boolean).map((segment) => {
    try {
      return decodeURIComponent(segment);
    } catch {
      return segment;
    }
  });

  if (segments.length === 0) return { name: "home" };
  const [head, ...rest] = segments;

  if (head === "invite" && rest.length) {
    // Токен может содержать «/» — склеиваем хвост обратно.
    return { name: "invite", token: rest.join("/") };
  }
  if (head === "login") {
    const next = new URLSearchParams(search).get("next") || "";
    return { name: "login", next: isSafeInternalPath(next) ? next : "" };
  }
  if (head === "address" && rest.length) {
    return { name: "address", id: rest[0] };
  }
  if (head === "legal" && rest.length) {
    const doc = LEGAL_DOCS.find((item) => item === rest[0]);
    if (doc) return { name: "legal", doc };
  }
  if (head === "app") {
    return { name: "cabinet", section: rest[0] || null, id: rest[1] || null };
  }
  // Неизвестный путь — не показываем «404», просто возвращаем на главную.
  return { name: "home" };
}

/** Разбор пути целиком («/app/applications?x=1»), как он приходит в `next`. */
export function parsePath(path: string): Route {
  const queryAt = path.indexOf("?");
  return queryAt === -1
    ? parseRoute(path)
    : parseRoute(path.slice(0, queryAt), path.slice(queryAt));
}

export function routeToPath(route: Route): string {
  switch (route.name) {
    case "home":
      return "/";
    case "address":
      return `/address/${encodeURIComponent(route.id)}`;
    case "legal":
      return `/legal/${route.doc}`;
    case "login":
      return route.next ? `/login?next=${encodeURIComponent(route.next)}` : "/login";
    case "invite":
      return `/invite/${encodeURIComponent(route.token)}`;
    case "cabinet": {
      if (!route.section) return "/app";
      const base = `/app/${encodeURIComponent(route.section)}`;
      return route.id ? `${base}/${encodeURIComponent(route.id)}` : base;
    }
  }
}

function currentDepth(): number {
  const state = window.history.state as Record<string, unknown> | null;
  const depth = state?.[DEPTH_KEY];
  return typeof depth === "number" ? depth : 0;
}

export type Navigate = (route: Route, options?: { replace?: boolean }) => void;

export type Router = {
  route: Route;
  navigate: Navigate;
  /** Шаг назад по истории; если возвращаться некуда — уводит на главную. */
  back: () => void;
  /** Есть ли в истории свой же экран, куда безопасно вернуться. */
  canGoBack: boolean;
};

export function useRouter(): Router {
  const [route, setRoute] = useState<Route>(() =>
    parseRoute(window.location.pathname, window.location.search),
  );
  const [depth, setDepth] = useState<number>(currentDepth);

  useEffect(() => {
    // Первая запись истории (прямой заход, F5) своего state не имеет —
    // проставляем глубину 0, чтобы кнопка «Назад» знала, что уходить некуда.
    if (currentDepth() === 0 && (window.history.state as Record<string, unknown> | null)?.[DEPTH_KEY] == null) {
      window.history.replaceState({ [DEPTH_KEY]: 0 }, "", window.location.href);
    }

    function handlePopState() {
      setRoute(parseRoute(window.location.pathname, window.location.search));
      setDepth(currentDepth());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = useCallback<Navigate>((next, options) => {
    const path = routeToPath(next);
    const current = `${window.location.pathname}${window.location.search}`;

    if (path === current) {
      // Тот же адрес — синхронизируем только состояние (например, после
      // нормализации раздела кабинета), новую запись в историю не плодим.
      setRoute(next);
      return;
    }

    if (options?.replace) {
      window.history.replaceState({ [DEPTH_KEY]: currentDepth() }, "", path);
    } else {
      const nextDepth = currentDepth() + 1;
      window.history.pushState({ [DEPTH_KEY]: nextDepth }, "", path);
      setDepth(nextDepth);
    }
    setRoute(next);
  }, []);

  const back = useCallback(() => {
    if (currentDepth() > 0) {
      window.history.back();
      return;
    }
    // Пришли по прямой ссылке — возвращаться внутри приложения некуда.
    navigate({ name: "home" });
  }, [navigate]);

  return { route, navigate, back, canGoBack: depth > 0 };
}
