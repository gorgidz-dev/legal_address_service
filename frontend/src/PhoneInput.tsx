import { InputHTMLAttributes } from "react";

/**
 * Russian phone mask "+7 (XXX) XXX-XX-XX".
 * Stores formatted text; backend normalises to E.164 on submit.
 * Leading 8 or 7 in pasted strings is collapsed into the +7 prefix.
 */
export function formatRuPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 15);
  if (!digits) return "";
  // Strip the country code if it's the Russian 7 or the legacy 8.
  let body = digits;
  if (body.startsWith("8")) body = body.slice(1);
  else if (body.startsWith("7")) body = body.slice(1);
  body = body.slice(0, 10);
  let out = "+7";
  if (body.length > 0) out += ` (${body.slice(0, 3)}`;
  if (body.length >= 3) out += ")";
  if (body.length > 3) out += ` ${body.slice(3, 6)}`;
  if (body.length > 6) out += `-${body.slice(6, 8)}`;
  if (body.length > 8) out += `-${body.slice(8, 10)}`;
  return out;
}

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
  value: string;
  onChange: (value: string) => void;
};

export function PhoneInput({ value, onChange, placeholder, ...rest }: Props) {
  return (
    <input
      {...rest}
      type="tel"
      inputMode="tel"
      autoComplete="tel"
      placeholder={placeholder ?? "+7 (___) ___-__-__"}
      value={value}
      onChange={(event) => onChange(formatRuPhone(event.target.value))}
    />
  );
}
