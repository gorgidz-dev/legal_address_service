import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../models/application.dart';
import '../../theme/tokens.dart';
import '../../widgets/ds.dart';

/// Заявка детально — артборд «06 · Заявка — детально».
///
/// Таймлайн строится из событий заявки (events с бэка), а не из
/// вымышленных шагов: реальный маршрут заявки виден как есть.
class RequestDetailScreen extends StatelessWidget {
  const RequestDetailScreen({super.key, required this.application});

  final ClientApplication application;

  @override
  Widget build(BuildContext context) {
    final meta = application.meta;
    final awaitingPayment = application.status == 'awaiting_payment';
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      appBar: AppBar(
        backgroundColor: DsColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: BackButton(color: DsColors.text, onPressed: context.pop),
        title: Text('Заявки', style: DsText.headingSm),
        shape: const Border(bottom: BorderSide(color: DsColors.borderSoft)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 28),
        children: [
          Text(application.fullAddress, style: DsText.headingLg),
          const SizedBox(height: 10),
          Row(
            children: [
              StatusBadge(status: application.status),
              const SizedBox(width: 8),
              if (application.companyName != null)
                Expanded(
                  child: Text(
                    application.companyName!,
                    style: DsText.caption,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 18),
          DsCard(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Статус заявки'),
                const SizedBox(height: 14),
                if (application.events.isEmpty)
                  Text(
                    'Событий пока нет — заявка на стороне сервиса. '
                    'Текущий статус: ${meta.label}.',
                    style: DsText.muted,
                  )
                else
                  _Timeline(events: application.events),
              ],
            ),
          ),
          const SizedBox(height: 14),
          DsCard(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SectionLabel('К оплате'),
                          const SizedBox(height: 4),
                          Text(
                            formatRub(application.priceTotal),
                            style: DsText.displayMd.copyWith(fontSize: 24),
                          ),
                        ],
                      ),
                    ),
                    if (awaitingPayment)
                      const DsButton(
                        label: 'Оплатить',
                        // Оплата в приложении не реализована: счёт и статусы —
                        // на вебе. Кнопка появится вместе с платёжным модулем.
                        onPressed: null,
                      ),
                  ],
                ),
                if (application.priceLines.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Divider(height: 1, color: Color(0xFFEEF0F4)),
                  const SizedBox(height: 12),
                  for (final line in application.priceLines)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(line.label, style: DsText.muted),
                          ),
                          Text(
                            formatRub(line.amount),
                            style: DsText.bodySm
                                .copyWith(fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ),
                ],
                if (awaitingPayment) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Оплата — по счёту из личного кабинета на uradres.net. '
                    'Оплата из приложения появится позже.',
                    style: DsText.caption,
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 22),
          const SectionLabel('Параметры'),
          const SizedBox(height: 12),
          DsCard(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: Column(
              children: [
                _kv('Срок аренды',
                    application.termMonths == null
                        ? '—'
                        : '${application.termMonths} мес.'),
                _kv('Собственник', application.providerName),
                _kv('Тип',
                    application.type == 'address_change'
                        ? 'Смена адреса'
                        : 'Регистрация новой компании'),
                _kv('Создана',
                    DateFormat('dd.MM.yyyy').format(application.createdAt)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _kv(String key, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 130,
            child: Text(key, style: DsText.muted),
          ),
          Expanded(
            child: Text(
              value,
              style: DsText.bodySm.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

class _Timeline extends StatelessWidget {
  const _Timeline({required this.events});

  final List<ApplicationEvent> events;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var i = 0; i < events.length; i++)
          _row(events[i], isLast: i == events.length - 1, isCurrent: i == events.length - 1),
      ],
    );
  }

  Widget _row(ApplicationEvent event, {required bool isLast, required bool isCurrent}) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 16,
            child: Column(
              children: [
                Container(
                  width: isCurrent ? 14 : 10,
                  height: isCurrent ? 14 : 10,
                  margin: const EdgeInsets.only(top: 3),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: DsColors.indigo500,
                    border: isCurrent
                        ? Border.all(color: DsColors.indigo100, width: 3)
                        : null,
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      margin: const EdgeInsets.only(top: 3),
                      color: DsColors.indigo100,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    event.title,
                    style: isCurrent
                        ? DsText.headingSm.copyWith(color: DsColors.brandFg)
                        : DsText.body.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    DateFormat('dd.MM.yyyy HH:mm').format(event.createdAt.toLocal()),
                    style: DsText.caption,
                  ),
                  if (event.message.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      event.message,
                      style: DsText.bodySm.copyWith(color: DsColors.slate700),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
