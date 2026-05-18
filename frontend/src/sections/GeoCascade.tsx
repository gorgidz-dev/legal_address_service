/**
 * Каскадный фильтр Регион → Город → ИФНС.
 *
 * Дерево грузится один раз (/marketplace/geo), каскад — в памяти.
 * Смена региона сбрасывает город и ИФНС; смена города — ИФНС.
 */
import { Building2, MapPin } from "lucide-react";
import type { GeoRegion } from "../types";

export type GeoSelection = {
  region: string;
  geoCity: string;
  fnsOfficeId: string;
};

type Props = {
  tree: GeoRegion[];
  value: GeoSelection;
  onChange: (next: GeoSelection) => void;
};

export function GeoCascade({ tree, value, onChange }: Props) {
  const region = tree.find((r) => r.region === value.region) || null;
  const city = region?.cities.find((c) => c.city === value.geoCity) || null;

  return (
    <>
      <label className="ds-configurator__field">
        <span className="ds-configurator__label">
          <MapPin size={14} /> Регион
        </span>
        <select
          className="ds-configurator__input"
          value={value.region}
          onChange={(e) =>
            onChange({ region: e.target.value, geoCity: "", fnsOfficeId: "" })
          }
        >
          <option value="">Любой</option>
          {tree.map((r) => (
            <option key={r.region} value={r.region}>
              {r.region} · {r.count}
            </option>
          ))}
        </select>
      </label>

      <label className="ds-configurator__field">
        <span className="ds-configurator__label">
          <MapPin size={14} /> Город
        </span>
        <select
          className="ds-configurator__input"
          value={value.geoCity}
          disabled={!region}
          onChange={(e) =>
            onChange({ ...value, geoCity: e.target.value, fnsOfficeId: "" })
          }
        >
          <option value="">{region ? "Любой" : "Сначала регион"}</option>
          {region?.cities.map((c) => (
            <option key={c.city} value={c.city}>
              {c.city} · {c.count}
            </option>
          ))}
        </select>
      </label>

      <label className="ds-configurator__field">
        <span className="ds-configurator__label">
          <Building2 size={14} /> ИФНС
        </span>
        <select
          className="ds-configurator__input"
          value={value.fnsOfficeId}
          disabled={!city}
          onChange={(e) => onChange({ ...value, fnsOfficeId: e.target.value })}
        >
          <option value="">{city ? "Любая" : "Сначала город"}</option>
          {city?.offices.map((o) => (
            <option key={o.id} value={o.id}>
              № {o.short_number ?? "—"} · {o.count}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
