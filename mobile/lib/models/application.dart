import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// Тон статуса — какой парой фон/текст красится бейдж.
///
/// Правило тонов дословно из frontend/src/status.ts:
///  success — подтверждённый факт или хороший исход;
///  brand   — ждём действия или денег от клиента, это главный призыв;
///  info    — процесс идёт, вмешательство не нужно;
///  warning — нужно действие человека;
///  danger  — срыв или открытая финансовая проблема;
///  neutral — пассив и архив.
enum StatusTone { brand, info, success, warning, danger, neutral }

extension StatusToneColors on StatusTone {
  Color get bg => switch (this) {
        StatusTone.brand => DsColors.brandBg,
        StatusTone.info => DsColors.infoBg,
        StatusTone.success => DsColors.successBg,
        StatusTone.warning => DsColors.warningBg,
        StatusTone.danger => DsColors.dangerBg,
        StatusTone.neutral => DsColors.neutralBg,
      };

  Color get fg => switch (this) {
        StatusTone.brand => DsColors.brandFg,
        StatusTone.info => DsColors.infoFg,
        StatusTone.success => DsColors.successFg,
        StatusTone.warning => DsColors.warningFg,
        StatusTone.danger => DsColors.dangerFg,
        StatusTone.neutral => DsColors.neutralFg,
      };
}

class StatusMeta {
  const StatusMeta(this.label, this.short, this.tone);

  /// Полная подпись: панель заявки, мобильная карточка.
  final String label;

  /// Короткая подпись, до 14 символов.
  final String short;
  final StatusTone tone;
}

/// Единственная карта статусов заявки — перенос frontend/src/status.ts
/// один в один. Новый статус на бэке без записи здесь покажет сырой код
/// значением (см. [statusMeta]) — это заметнее, чем пустой бейдж.
const Map<String, StatusMeta> kStatusMeta = {
  'draft': StatusMeta('Черновик', 'Черновик', StatusTone.neutral),
  'guarantee_issued': StatusMeta('Гарантийка выдана', 'Гарантийка', StatusTone.info),
  'awaiting_contract': StatusMeta('Ожидает договор', 'Ждёт договор', StatusTone.brand),
  'contract_signed': StatusMeta('Договор подписан', 'Подписан', StatusTone.success),
  'active': StatusMeta('Активна', 'Активна', StatusTone.success),
  'expired': StatusMeta('Истекла', 'Истекла', StatusTone.warning),
  'terminated': StatusMeta('Расторгнута', 'Расторгнута', StatusTone.danger),
  'awaiting_payment': StatusMeta('Ожидает оплату', 'Оплата', StatusTone.brand),
  'paid': StatusMeta('Оплачена', 'Оплачена', StatusTone.success),
  'admin_review': StatusMeta('Проверка администратора', 'Проверка', StatusTone.info),
  'needs_client_fix': StatusMeta('Нужны уточнения', 'Правки', StatusTone.warning),
  'assigned_to_owner': StatusMeta('Передана собственнику', 'У собственника', StatusTone.warning),
  'accepted_by_owner': StatusMeta('Принята собственником', 'Принята', StatusTone.info),
  'rejected_by_owner': StatusMeta('Отклонена собственником', 'Отказ', StatusTone.danger),
  'documents_preparing': StatusMeta('Готовятся документы', 'Подготовка', StatusTone.info),
  'documents_uploaded': StatusMeta('Документы загружены', 'Загружены', StatusTone.info),
  'documents_review': StatusMeta('Проверка документов', 'Документы', StatusTone.info),
  'documents_revision': StatusMeta('Доработка документов', 'Доработка', StatusTone.warning),
  'ready_for_client': StatusMeta('Готова к выдаче', 'Готово', StatusTone.success),
  'completed': StatusMeta('Завершена', 'Завершена', StatusTone.success),
  'cancelled': StatusMeta('Отменена', 'Отменена', StatusTone.neutral),
  'dispute': StatusMeta('Спор', 'Спор', StatusTone.danger),
  'refund_pending': StatusMeta('Возврат готовится', 'Возврат', StatusTone.danger),
  'refunded': StatusMeta('Возврат выполнен', 'Возвращено', StatusTone.neutral),
};

/// Статус может прийти значением, которого нет в карте (рассинхрон с бэком).
/// Показ сырого кода лучше пустого бейджа.
StatusMeta statusMeta(String? status) {
  final known = status == null ? null : kStatusMeta[status];
  if (known != null) return known;
  final raw = status ?? '—';
  return StatusMeta(raw, raw, StatusTone.neutral);
}

class ApplicationEvent {
  const ApplicationEvent({
    required this.id,
    required this.kind,
    required this.title,
    required this.message,
    required this.createdAt,
  });

  final String id;
  final String kind;
  final String title;
  final String message;
  final DateTime createdAt;

  factory ApplicationEvent.fromJson(Map<String, dynamic> json) =>
      ApplicationEvent(
        id: json['id'] as String,
        kind: json['kind'] as String? ?? '',
        title: json['title'] as String? ?? '',
        message: json['message'] as String? ?? '',
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}

class PriceLine {
  const PriceLine({required this.kind, required this.label, required this.amount});

  final String kind;
  final String label;

  /// Decimal с бэка сериализуется строкой — храним строкой, форматируем на месте.
  final String amount;

  factory PriceLine.fromJson(Map<String, dynamic> json) => PriceLine(
        kind: json['kind'] as String? ?? '',
        label: json['label'] as String? ?? '',
        amount: (json['amount'] ?? '0').toString(),
      );
}

/// Заявка клиента — GET /client/applications.
class ClientApplication {
  const ClientApplication({
    required this.id,
    required this.type,
    required this.status,
    required this.fullAddress,
    required this.roomNumber,
    required this.providerName,
    required this.companyName,
    required this.termMonths,
    required this.priceTotal,
    required this.priceLines,
    required this.events,
    required this.createdAt,
  });

  final String id;
  final String type;
  final String status;
  final String fullAddress;
  final String? roomNumber;
  final String providerName;
  final String? companyName;
  final int? termMonths;
  final String priceTotal;
  final List<PriceLine> priceLines;
  final List<ApplicationEvent> events;
  final DateTime createdAt;

  StatusMeta get meta => statusMeta(status);

  factory ClientApplication.fromJson(Map<String, dynamic> json) =>
      ClientApplication(
        id: json['id'] as String,
        type: json['type'] as String? ?? '',
        status: json['status'] as String? ?? '',
        fullAddress: json['full_address'] as String? ?? '',
        roomNumber: json['room_number'] as String?,
        providerName: json['provider_name'] as String? ?? '',
        companyName: json['company_name'] as String?,
        termMonths: json['term_months'] as int?,
        priceTotal: (json['price_total'] ?? '0').toString(),
        priceLines: [
          for (final line in (json['price_lines'] as List? ?? const []))
            PriceLine.fromJson(line as Map<String, dynamic>),
        ],
        events: [
          for (final event in (json['events'] as List? ?? const []))
            ApplicationEvent.fromJson(event as Map<String, dynamic>),
        ],
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}
