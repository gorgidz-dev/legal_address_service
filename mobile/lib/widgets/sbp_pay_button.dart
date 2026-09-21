import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/tokens.dart';

/// Кнопка оплаты в фирменном стиле СБП.
///
/// Оформление — по «Рекомендациям по дизайну элементов и брендированию
/// экранов оплаты» НСПК (sbp.nspk.ru/banks → «Руководство для e-commerce»),
/// так же, как на вебе (frontend/src/payment/SbpPayButton.tsx):
/// - фон #1d1346 на светлом экране;
/// - вариант с call-to-action «Оплатить» + знак СБП;
/// - высота как у остальных кнопок приложения ([DsButton] — 44);
/// - знак официальный (assets/sbp/sbp-logo-on-dark.svg — векторы из архива
///   НСПК logo.zip без изменений), не перекрашивается и не растягивается.
class SbpPayButton extends StatelessWidget {
  const SbpPayButton({super.key, required this.onPressed, this.busy = false});

  static const background = Color(0xFF1D1346);

  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Оплатить через СБП',
      excludeSemantics: true,
      child: Material(
        color: background,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(DsRadii.button),
        ),
        child: InkWell(
          onTap: busy ? null : onPressed,
          borderRadius: BorderRadius.circular(DsRadii.button),
          child: Container(
            constraints: const BoxConstraints(minHeight: 44),
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
            child: Row(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (busy) ...[
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                ],
                Text(
                  'Оплатить',
                  style: DsText.headingSm.copyWith(color: Colors.white),
                ),
                const SizedBox(width: 12),
                SvgPicture.asset(
                  'assets/sbp/sbp-logo-on-dark.svg',
                  height: 24,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
