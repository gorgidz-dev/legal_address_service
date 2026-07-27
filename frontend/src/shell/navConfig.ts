/**
 * Разделы кабинета по ролям — один источник вместо трёх наборов кнопок.
 *
 * Идентификаторы разделов не меняются: это сегменты URL /app/<section>, они
 * уже разошлись по ссылкам в письмах и push-уведомлениях. Меняется только то,
 * как они сгруппированы и подписаны.
 */
import {
  Building2,
  FileClock,
  FileText,
  FolderOpen,
  Home,
  Image as ImageIcon,
  MessageSquare,
  Plus,
  Settings,
  ShieldCheck,
  Star,
  UserPlus
} from "lucide-react";
import type { ComponentType } from "react";
import type { UserRole } from "../types";

export type NavIcon = ComponentType<{ size?: number | string; strokeWidth?: number }>;

export type NavItem = {
  /** Сегмент URL. Менять нельзя — ломает существующие ссылки. */
  id: string;
  label: string;
  icon: NavIcon;
  /** Короткая подпись для нижней панели на телефоне. */
  shortLabel?: string;
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

const CLIENT_GROUPS: NavGroup[] = [
  {
    title: "Кабинет",
    items: [
      { id: "applications", label: "Заявки", icon: FolderOpen },
      { id: "chats", label: "Чаты", icon: MessageSquare }
    ]
  }
];

const OWNER_GROUPS: NavGroup[] = [
  {
    title: "Кабинет",
    items: [
      { id: "applications", label: "Заявки", icon: FolderOpen },
      { id: "addresses", label: "Адреса", icon: Home },
      { id: "chats", label: "Чаты", icon: MessageSquare }
    ]
  }
];

/**
 * У оператора тринадцать разделов, и до этой правки они шли одним плоским
 * списком, где «Услуги адресов» стояли между «Модерацией адресов» и «Чатами».
 * Группы не убирают лишние разделы — это отдельная задача (объединить четыре
 * экрана про адрес во вкладки), — но перестают заставлять читать список
 * целиком, чтобы найти нужное.
 */
const ADMIN_GROUPS: NavGroup[] = [
  {
    title: "Заявки",
    items: [
      { id: "applications", label: "Заявки", icon: FolderOpen },
      { id: "new", label: "Новая заявка", icon: Plus, shortLabel: "Новая" },
      { id: "address-chats", label: "Чаты", icon: MessageSquare }
    ]
  },
  {
    title: "Адреса",
    items: [
      { id: "addresses", label: "Помещения", icon: Home },
      { id: "address-moderation", label: "Модерация адресов", icon: FileText, shortLabel: "Модерация" },
      { id: "address-services", label: "Услуги адресов", icon: Settings, shortLabel: "Услуги" },
      { id: "photos", label: "Фото на модерацию", icon: ImageIcon, shortLabel: "Фото" }
    ]
  },
  {
    title: "Собственники",
    items: [
      { id: "providers", label: "Собственники", icon: Building2 },
      { id: "provider-requests", label: "Заявки собственников", icon: UserPlus, shortLabel: "Подключения" },
      { id: "review-moderation", label: "Отзывы на модерацию", icon: Star, shortLabel: "Отзывы" }
    ]
  },
  {
    title: "Система",
    items: [
      { id: "registry", label: "Действующие клиенты", icon: FileClock, shortLabel: "Клиенты" },
      { id: "templates", label: "Шаблоны", icon: Settings },
      { id: "access", label: "Доступ", icon: ShieldCheck }
    ]
  }
];

/** Роли manager и lawyer остались от внутренних процессов: у них нет админских разделов. */
const STAFF_GROUPS: NavGroup[] = ADMIN_GROUPS.map((group) => ({
  ...group,
  items: group.items.filter((item) =>
    ["applications", "new", "registry", "providers", "addresses", "templates"].includes(item.id)
  )
})).filter((group) => group.items.length > 0);

export function navGroupsFor(role: UserRole): NavGroup[] {
  if (role === "client") return CLIENT_GROUPS;
  if (role === "owner") return OWNER_GROUPS;
  if (role === "admin") return ADMIN_GROUPS;
  return STAFF_GROUPS;
}

export function navItemsFor(role: UserRole): NavItem[] {
  return navGroupsFor(role).flatMap((group) => group.items);
}

export function sectionLabel(role: UserRole, id: string): string {
  return navItemsFor(role).find((item) => item.id === id)?.label || "Кабинет";
}

export const ROLE_CAPTIONS: Record<UserRole, string> = {
  admin: "оператор",
  manager: "менеджер",
  lawyer: "юрист",
  client: "клиент",
  owner: "собственник"
};
