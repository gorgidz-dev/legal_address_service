import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/application.dart';
import '../theme/tokens.dart';

/// Примитивы дизайн-системы — мобильные двойники `.ds-*` компонентов веба.

final NumberFormat _rub = NumberFormat('#,##0', 'ru_RU');

/// «28000.00» → «28 000 ₽». Цены с бэка приходят строками.
String formatRub(String amount) {
  final value = double.tryParse(amount) ?? 0;
  return '${_rub.format(value)} ₽';
}

enum DsButtonKind { primary, secondary, ghost }

class DsButton extends StatelessWidget {
  const DsButton({
    super.key,
    required this.label,
    this.onPressed,
    this.kind = DsButtonKind.primary,
    this.expanded = false,
    this.busy = false,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final DsButtonKind kind;
  final bool expanded;
  final bool busy;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final (bg, fg, side) = switch (kind) {
      DsButtonKind.primary => (
          DsColors.indigo500,
          Colors.white,
          BorderSide.none
        ),
      DsButtonKind.secondary => (
          DsColors.surface,
          DsColors.text,
          const BorderSide(color: DsColors.slate200)
        ),
      DsButtonKind.ghost => (
          Colors.transparent,
          DsColors.indigo500,
          BorderSide.none
        ),
    };
    final child = busy
        ? SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(strokeWidth: 2, color: fg),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 18, color: fg),
                const SizedBox(width: 8),
              ],
              Text(
                label,
                style: DsText.headingSm.copyWith(color: fg),
              ),
            ],
          );
    final button = Material(
      color: bg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(DsRadii.button),
        side: side,
      ),
      child: InkWell(
        onTap: busy ? null : onPressed,
        borderRadius: BorderRadius.circular(DsRadii.button),
        child: Container(
          constraints: const BoxConstraints(minHeight: 44),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 11),
          alignment: Alignment.center,
          child: child,
        ),
      ),
    );
    return expanded ? SizedBox(width: double.infinity, child: button) : button;
  }
}

/// Чип фильтра. Выбранный заливается indigo-950 (тёмным, не брендовым),
/// чтобы не спорить с кнопками — правило системы.
class DsChip extends StatelessWidget {
  const DsChip({
    super.key,
    required this.label,
    this.selected = false,
    this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? DsColors.indigo950 : DsColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(DsRadii.pill),
        side: BorderSide(
          color: selected ? DsColors.indigo950 : DsColors.slate200,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(DsRadii.pill),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: DsText.bodySm.copyWith(
                  fontWeight: FontWeight.w500,
                  color: selected ? Colors.white : DsColors.text,
                ),
              ),
              if (selected) ...[
                const SizedBox(width: 6),
                const Icon(Icons.close, size: 13, color: Colors.white),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Статус-бейдж: pill, 11px ЗАГЛАВНЫМИ, пара фон/текст из тона.
class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.status, this.compact = false});

  final String status;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final meta = statusMeta(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: meta.tone.bg,
        borderRadius: BorderRadius.circular(DsRadii.pill),
      ),
      child: Text(
        (compact ? meta.short : meta.label).toUpperCase(),
        style: DsText.label.copyWith(fontSize: 10, color: meta.tone.fg),
      ),
    );
  }
}

/// Бейдж произвольного тона — «Скоро», «Просрочено» в календаре.
class ToneBadge extends StatelessWidget {
  const ToneBadge({super.key, required this.label, required this.tone});

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: tone.bg,
        borderRadius: BorderRadius.circular(DsRadii.pill),
      ),
      child: Text(
        label.toUpperCase(),
        style: DsText.label.copyWith(fontSize: 10, color: tone.fg),
      ),
    );
  }
}

/// Белая карточка с мягкой границей #ececff и индиго-тенью.
class DsCard extends StatelessWidget {
  const DsCard({super.key, required this.child, this.padding, this.onTap});

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final body = Container(
      decoration: BoxDecoration(
        color: DsColors.surface,
        borderRadius: BorderRadius.circular(DsRadii.card),
        border: Border.all(color: DsColors.borderSoft),
        boxShadow: DsShadows.card,
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: padding ?? EdgeInsets.zero,
        child: child,
      ),
    );
    if (onTap == null) return body;
    return GestureDetector(onTap: onTap, child: body);
  }
}

/// Плитка-заглушка вместо фото: единственный градиент системы + инициалы.
class InitialsTile extends StatelessWidget {
  const InitialsTile({
    super.key,
    required this.initials,
    this.size,
    this.fontSize = 36,
    this.radius = 0,
  });

  final String initials;
  final double? size;
  final double fontSize;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: DsColors.fallbackGradient,
        borderRadius: BorderRadius.circular(radius),
      ),
      alignment: Alignment.center,
      child: Text(
        initials,
        style: DsText.displayXl.copyWith(
          fontSize: fontSize,
          color: Colors.white,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

/// Сегмент-переключатель срока: трек slate-100, активная вкладка белая.
class DsSegmented extends StatelessWidget {
  const DsSegmented({
    super.key,
    required this.options,
    required this.selectedIndex,
    required this.onChanged,
  });

  final List<String> options;
  final int selectedIndex;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: DsColors.slate100,
        borderRadius: BorderRadius.circular(DsRadii.button),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < options.length; i++)
            GestureDetector(
              onTap: () => onChanged(i),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                decoration: BoxDecoration(
                  color: i == selectedIndex ? DsColors.surface : null,
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: i == selectedIndex
                      ? const [
                          BoxShadow(
                            color: Color(0x140B0A2E),
                            blurRadius: 2,
                            offset: Offset(0, 1),
                          ),
                        ]
                      : null,
                ),
                child: Text(
                  options[i],
                  style: DsText.bodySm.copyWith(
                    fontWeight: FontWeight.w600,
                    color: i == selectedIndex
                        ? DsColors.indigo500
                        : DsColors.textMuted,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Поле ввода в стиле .ds-input: белое, граница slate-200, фокус — индиго.
class DsTextField extends StatelessWidget {
  const DsTextField({
    super.key,
    required this.label,
    this.controller,
    this.hint,
    this.obscure = false,
    this.keyboardType,
    this.textInputAction,
  });

  final String label;
  final TextEditingController? controller;
  final String? hint;
  final bool obscure;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;

  @override
  Widget build(BuildContext context) {
    OutlineInputBorder border(Color color, [double width = 1]) =>
        OutlineInputBorder(
          borderRadius: BorderRadius.circular(DsRadii.input),
          borderSide: BorderSide(color: color, width: width),
        );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(), style: DsText.label),
        const SizedBox(height: 7),
        TextField(
          controller: controller,
          obscureText: obscure,
          keyboardType: keyboardType,
          textInputAction: textInputAction,
          style: DsText.body,
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: DsText.body.copyWith(color: DsColors.slate400),
            filled: true,
            fillColor: DsColors.surface,
            isDense: true,
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
            enabledBorder: border(DsColors.slate200),
            focusedBorder: border(DsColors.indigo500, 1.5),
          ),
        ),
      ],
    );
  }
}

/// Ярлык секции — 11px ЗАГЛАВНЫМИ, как в кабинете веба.
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text.toUpperCase(), style: DsText.label);
  }
}

/// Круглый аватар с инициалами — шапка кабинета.
class InitialsAvatar extends StatelessWidget {
  const InitialsAvatar({super.key, required this.initials, this.size = 36});

  final String initials;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: const BoxDecoration(
        gradient: DsColors.fallbackGradient,
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(
        initials,
        style: DsText.bodySm.copyWith(
          color: Colors.white,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

/// Заглушки состояний списка: загрузка, ошибка, пусто.
class ListState extends StatelessWidget {
  const ListState.loading({super.key})
      : message = null,
        onRetry = null,
        _loading = true;

  const ListState.error(this.message, {super.key, this.onRetry})
      : _loading = false;

  const ListState.empty(this.message, {super.key})
      : onRetry = null,
        _loading = false;

  final String? message;
  final VoidCallback? onRetry;
  final bool _loading;

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(48),
          child: CircularProgressIndicator(color: DsColors.indigo500),
        ),
      );
    }
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              message ?? '',
              style: DsText.muted,
              textAlign: TextAlign.center,
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              DsButton(
                label: 'Повторить',
                kind: DsButtonKind.secondary,
                onPressed: onRetry,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
