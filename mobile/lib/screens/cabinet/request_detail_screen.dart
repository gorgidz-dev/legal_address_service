import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/client.dart';
import '../../api/repositories.dart';
import '../../models/application.dart';
import '../../models/payment.dart';
import '../../theme/tokens.dart';
import '../../widgets/ds.dart';
import '../../widgets/sbp_pay_button.dart';

/// Заявка детально — артборд «06 · Заявка — детально».
///
/// Таймлайн строится из событий заявки (events с бэка), а не из
/// вымышленных шагов: реальный маршрут заявки виден как есть.
///
/// Оплата — как на вебе: экран только читает текущий платёж, заказ у банка
/// создаётся кнопкой «Оплатить» (стиль СБП), форма Т-Банка открывается во
/// встроенной вкладке браузера, а экран ждёт подтверждения оплаты.
class RequestDetailScreen extends StatefulWidget {
  const RequestDetailScreen({
    super.key,
    required this.application,
    required this.cabinet,
  });

  final ClientApplication application;
  final CabinetRepository cabinet;

  @override
  State<RequestDetailScreen> createState() => _RequestDetailScreenState();
}

class _RequestDetailScreenState extends State<RequestDetailScreen>
    with WidgetsBindingObserver {
  /// Сколько ждать подтверждения банка после ухода на форму оплаты. Форма
  /// открыта во встроенной вкладке браузера, а на iOS её закрытие приложению
  /// не видно, поэтому отсчёт идёт с момента ухода, а не возврата.
  static const _waitWindow = Duration(minutes: 10);
  static const _pollEvery = Duration(seconds: 3);

  late ClientApplication _application = widget.application;
  Payment? _payment;
  bool _paymentLoading = false;
  bool _busy = false;
  String? _payError;
  DateTime? _waitUntil;
  Timer? _poll;

  bool get _awaitingPayment => _application.status == 'awaiting_payment';
  bool get _waiting => _waitUntil != null && (_payment?.isOpen ?? false);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (_awaitingPayment) _loadPayment();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Вернулись из вкладки банка (Android закрыл Custom Tab — приложение
    // снова активно): проверяем сразу, не дожидаясь очередного тика.
    if (state == AppLifecycleState.resumed && _waiting) _checkOnce();
  }

  Future<void> _loadPayment() async {
    setState(() => _paymentLoading = true);
    try {
      final payment =
          await widget.cabinet.paymentForApplication(_application.id);
      if (mounted) setState(() => _payment = payment);
    } catch (_) {
      // Без текущего платежа кнопка всё равно работает: initiate сам найдёт
      // или создаст платёж.
    } finally {
      if (mounted) setState(() => _paymentLoading = false);
    }
  }

  Future<void> _pay() async {
    setState(() {
      _busy = true;
      _payError = null;
    });
    try {
      final payment = await widget.cabinet.initiatePayment(_application.id);
      if (!mounted) return;
      setState(() => _payment = payment);
      if (payment.isPaid) {
        await _onPaid();
        return;
      }
      final url = payment.paymentUrl;
      if (payment.provider != 'tbank' || url == null) {
        setState(() => _payError = 'Онлайн-оплата сейчас недоступна. '
            'Напишите в поддержку — поможем оплатить.');
        return;
      }
      // Custom Tabs / SFSafariViewController. WebView для платёжной формы
      // Т-Банк запрещает: пользователь должен видеть адрес и замок браузера.
      final opened = await launchUrl(
        Uri.parse(url),
        mode: LaunchMode.inAppBrowserView,
      );
      if (!mounted) return;
      if (!opened) {
        setState(() => _payError = 'Не удалось открыть страницу оплаты.');
        return;
      }
      _startWaiting();
    } catch (error) {
      if (mounted) setState(() => _payError = apiErrorMessage(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _startWaiting() {
    _poll?.cancel();
    setState(() => _waitUntil = DateTime.now().add(_waitWindow));
    _poll = Timer.periodic(_pollEvery, (_) => _checkOnce());
  }

  Future<void> _checkOnce() async {
    final payment = _payment;
    final until = _waitUntil;
    if (payment == null || until == null) return;
    if (DateTime.now().isAfter(until)) {
      _poll?.cancel();
      if (mounted) setState(() => _waitUntil = null);
      return;
    }
    try {
      // GET /payments/{id} сам сверяется с банком (не чаще раза в 20 с).
      final fresh = await widget.cabinet.payment(payment.id);
      if (!mounted) return;
      setState(() => _payment = fresh);
      if (fresh.isPaid) {
        _poll?.cancel();
        await _onPaid();
      } else if (!fresh.isOpen) {
        // Банк закрыл платёж без оплаты (отказ, истёк срок) — ждать нечего.
        _poll?.cancel();
        setState(() => _waitUntil = null);
      }
    } catch (_) {
      // Сбой одного опроса не повод пугать — следующий повторит.
    }
  }

  /// Оплата подтверждена: подтягиваем заявку со свежим статусом и лентой.
  Future<void> _onPaid() async {
    setState(() => _waitUntil = null);
    try {
      final all = await widget.cabinet.applications();
      final fresh = all.where((item) => item.id == _application.id);
      if (mounted && fresh.isNotEmpty) {
        setState(() => _application = fresh.first);
      }
    } catch (_) {
      // Статус обновится при следующем открытии списка.
    }
  }

  @override
  Widget build(BuildContext context) {
    final application = _application;
    final meta = application.meta;
    final awaitingPayment = _awaitingPayment;
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
                const SectionLabel('К оплате'),
                const SizedBox(height: 4),
                Text(
                  formatRub(application.priceTotal),
                  style: DsText.displayMd.copyWith(fontSize: 24),
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
                  const SizedBox(height: 14),
                  _paymentBlock(),
                ] else if (_payment?.isPaid ?? false) ...[
                  const SizedBox(height: 14),
                  _note(
                    'Оплата получена. Заявка ушла на проверку администратора.',
                    bg: DsColors.successBg,
                    fg: DsColors.successFg,
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

  Widget _paymentBlock() {
    final payment = _payment;
    if (_paymentLoading) {
      return const Center(
        child: SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    if (payment != null && payment.provider == 'manual_invoice') {
      return Text(
        'Оплата по счёту для юрлица: счёт и платёжное поручение — в личном '
        'кабинете на uradres.net.',
        style: DsText.caption,
      );
    }
    final processing = payment?.isProcessingAtBank ?? false;
    final refunding = payment != null &&
        (payment.status == 'refund_requested' || payment.status == 'refunded');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_waiting)
          _note(
            'Проверяем оплату в банке. Когда закончите на странице Т-Банка, '
            'вернитесь сюда — статус обновится сам.',
            busy: true,
          )
        else if (processing)
          _note(
            'Банк обрабатывает платёж. Как только он подтвердит оплату, '
            'заявка перейдёт в статус «Оплачена».',
          )
        else if (refunding)
          _note(
            'Предыдущий платёж по заявке возвращается банком. '
            'Оплатить заявку можно заново.',
          ),
        if (_waiting || processing) ...[
          const SizedBox(height: 10),
          DsButton(
            label: 'Проверить статус',
            kind: DsButtonKind.secondary,
            expanded: true,
            onPressed: () {
              if (!_waiting) _startWaiting();
              _checkOnce();
            },
          ),
        ] else ...[
          if (refunding) const SizedBox(height: 10),
          SbpPayButton(busy: _busy, onPressed: _pay),
          const SizedBox(height: 8),
          Text(
            'Откроется защищённая страница оплаты Т-Банка.',
            style: DsText.caption,
            textAlign: TextAlign.center,
          ),
        ],
        if (_payError != null) ...[
          const SizedBox(height: 10),
          _note(_payError!, bg: DsColors.dangerBg, fg: DsColors.dangerFg),
        ],
      ],
    );
  }

  Widget _note(
    String text, {
    Color bg = DsColors.infoBg,
    Color fg = DsColors.infoFg,
    bool busy = false,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(DsRadii.card),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (busy) ...[
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: fg),
            ),
            const SizedBox(width: 10),
          ],
          Expanded(
            child: Text(text, style: DsText.bodySm.copyWith(color: fg)),
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
