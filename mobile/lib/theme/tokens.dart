import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Дизайн-токены мобильного приложения.
///
/// Источник — frontend/src/design/tokens.css (система `--ds-*`, индиго,
/// светлая тема) и docs/design.md. Значения переносятся дословно: приложение
/// обязано совпадать с вебом, а не «вдохновляться» им.
abstract final class DsColors {
  // Indigo (бренд)
  static const indigo50 = Color(0xFFF0F1FD);
  static const indigo100 = Color(0xFFDDE0FA);
  static const indigo300 = Color(0xFF9AA1EB);
  static const indigo400 = Color(0xFF7D83E0);
  static const indigo500 = Color(0xFF5B5BD6);
  static const indigo600 = Color(0xFF4A47C2);
  static const indigo700 = Color(0xFF3B38A3);
  static const indigo950 = Color(0xFF0B0A2E);

  // Slate (нейтрали)
  static const slate100 = Color(0xFFF1F3F6);
  static const slate200 = Color(0xFFE2E6EC);
  static const slate300 = Color(0xFFCBD1DA);
  static const slate400 = Color(0xFF9BA3B1);
  static const slate500 = Color(0xFF64748B);
  static const slate700 = Color(0xFF334155);

  /// Граница карточек — мягче Slate-100 и холоднее.
  static const borderSoft = Color(0xFFECECFF);

  static const pageBg = Color(0xFFFAFBFC);
  static const surface = Color(0xFFFFFFFF);
  static const text = indigo950;
  static const textMuted = slate500;

  // Семантические пары (фон / текст) — только для бейджей и мелких подсказок.
  static const successBg = Color(0xFFDCFCE7);
  static const successFg = Color(0xFF166534);
  static const warningBg = Color(0xFFFEF3C7);
  static const warningFg = Color(0xFF92400E);
  static const dangerBg = Color(0xFFFEE2E2);
  static const dangerFg = Color(0xFF991B1B);
  static const infoBg = Color(0xFFDBEAFE);
  static const infoFg = Color(0xFF1E40AF);
  static const neutralBg = slate100;
  static const neutralFg = Color(0xFF475569);
  static const brandBg = indigo50;
  static const brandFg = indigo700;

  /// Рейтинг (звёзды) — как .ds-stars__fg в вебе.
  static const star = Color(0xFFF5A623);

  /// Единственный градиент системы — плитка-заглушка вместо фото.
  static const fallbackGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [indigo500, Color(0xFF8B87FF)],
  );

  /// Градиент логотипа (из frontend/public/logo.svg).
  static const logoGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [indigo600, indigo500, indigo400],
    stops: [0.0, 0.55, 1.0],
  );
}

abstract final class DsRadii {
  static const button = 8.0;
  static const card = 10.0;
  static const input = 10.0;
  static const modal = 14.0;
  static const pill = 999.0;
}

/// Тени едва заметные, с холодным индиго-подтоном — никогда серые и тяжёлые.
abstract final class DsShadows {
  static const card = [
    BoxShadow(color: Color(0x0F0B0A2E), blurRadius: 3, offset: Offset(0, 1)),
    BoxShadow(color: Color(0x0A0B0A2E), blurRadius: 2, offset: Offset(0, 1)),
  ];
  static const raised = [
    BoxShadow(color: Color(0x140B0A2E), blurRadius: 12, offset: Offset(0, 4)),
    BoxShadow(color: Color(0x0A0B0A2E), blurRadius: 4, offset: Offset(0, 2)),
  ];
}

abstract final class DsText {
  static TextStyle get displayXl => GoogleFonts.inter(
        fontSize: 30, fontWeight: FontWeight.w800, height: 1.06,
        letterSpacing: -0.9, color: DsColors.text);
  static TextStyle get displayMd => GoogleFonts.inter(
        fontSize: 22, fontWeight: FontWeight.w800, height: 1.15,
        letterSpacing: -0.44, color: DsColors.text);
  static TextStyle get headingLg => GoogleFonts.inter(
        fontSize: 18, fontWeight: FontWeight.w800, height: 1.3,
        letterSpacing: -0.36, color: DsColors.text);
  static TextStyle get headingMd => GoogleFonts.inter(
        fontSize: 16, fontWeight: FontWeight.w700, height: 1.3,
        letterSpacing: -0.24, color: DsColors.text);
  static TextStyle get headingSm => GoogleFonts.inter(
        fontSize: 15, fontWeight: FontWeight.w600, height: 1.35,
        color: DsColors.text);
  static TextStyle get body => GoogleFonts.inter(
        fontSize: 14, fontWeight: FontWeight.w400, height: 1.45,
        color: DsColors.text);
  static TextStyle get bodySm => GoogleFonts.inter(
        fontSize: 13, fontWeight: FontWeight.w400, height: 1.45,
        color: DsColors.text);
  static TextStyle get muted => GoogleFonts.inter(
        fontSize: 13, fontWeight: FontWeight.w400, height: 1.45,
        color: DsColors.textMuted);
  static TextStyle get caption => GoogleFonts.inter(
        fontSize: 12, fontWeight: FontWeight.w400,
        color: DsColors.textMuted);

  /// Подпись 11px ЗАГЛАВНЫМИ с разрядкой — ярлыки секций и полей.
  static TextStyle get label => GoogleFonts.inter(
        fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 0.66,
        color: DsColors.textMuted);

  /// Цена — крупно индиго, как .ds-card__price.
  static TextStyle get price => GoogleFonts.inter(
        fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.44,
        color: DsColors.indigo500);
}
