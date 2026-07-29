/**
 * Характеристики помещения — единый справочник для карточки и кабинета.
 *
 * Один источник, как у статусов заявок (status.ts): подпись и иконка не должны
 * разъезжаться между витриной и формой собственника. Порядок здесь задаёт
 * порядок галочек в кабинете; в карточке порядок тот, что выбрал собственник.
 *
 * Значения синхронизированы с app/enums.py::AddressAmenity — расхождение
 * ловится тестом tests/test_amenities_sync.py.
 */
import {
  Building2,
  CircleParking,
  ConciergeBell,
  ShieldCheck,
  TrainFront,
  type LucideIcon,
} from "lucide-react";
import type { AddressAmenity } from "./types";

export type AmenityMeta = {
  label: string;
  icon: LucideIcon;
};

export const AMENITIES: Record<AddressAmenity, AmenityMeta> = {
  metro: { label: "Рядом с метро", icon: TrainFront },
  parking: { label: "Парковка", icon: CircleParking },
  security: { label: "Охрана", icon: ShieldCheck },
  concierge: { label: "Консьерж", icon: ConciergeBell },
  elevator: { label: "Лифт", icon: Building2 },
};

export const AMENITY_ORDER: AddressAmenity[] = [
  "metro",
  "parking",
  "security",
  "concierge",
  "elevator",
];

/** Отбрасывает значения, которых нет в справочнике: бэкенд мог уехать вперёд. */
export function knownAmenities(values: readonly string[] | null | undefined): AddressAmenity[] {
  if (!values) return [];
  return values.filter((v): v is AddressAmenity => v in AMENITIES);
}
