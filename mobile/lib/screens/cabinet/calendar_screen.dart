import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../api/client.dart';
import '../../api/repositories.dart';
import '../../models/application.dart';
import '../../models/misc.dart';
import '../../theme/tokens.dart';
import '../../widgets/ds.dart';

/// Календарь аренды — артборд «07 · Календарь».
///
/// Данные — GET /client/lease-calendar: сроки действующих договоров.
/// renewal_status с бэка: active | due_soon | overdue.
class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key, required this.cabinet, required this.auth});

  final CabinetRepository cabinet;
  final AuthState auth;

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  List<LeaseCalendarItem>? _items;
  Object? _error;
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final items = await widget.cabinet.leaseCalendar();
      if (!mounted) return;
      setState(() => _items = items);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      body: SafeArea(
        child: RefreshIndicator(
          color: DsColors.indigo500,
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 18, 16, 24),
            children: [
              Row(
                children: [
                  Expanded(
                      child: Text('Календарь', style: DsText.displayMd)),
                  InitialsAvatar(
                      initials: widget.auth.user?.initials ?? '·'),
                ],
              ),
              const SizedBox(height: 16),
              DsCard(
                padding: const EdgeInsets.all(16),
                child: _monthGrid(items ?? const []),
              ),
              const SizedBox(height: 20),
              const SectionLabel('События'),
              const SizedBox(height: 12),
              if (_error != null)
                ListState.error(apiErrorMessage(_error!), onRetry: _load)
              else if (items == null)
                const ListState.loading()
              else if (items.isEmpty)
                const ListState.empty(
                    'Действующих договоров нет — сроки появятся после '
                    'заключения аренды.')
              else
                for (final item in items
                  ..sort((a, b) => a.endDate.compareTo(b.endDate)))
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _EventRow(item: item),
                  ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _monthGrid(List<LeaseCalendarItem> items) {
    final monthTitle = toBeginningOfSentenceCase(
        DateFormat('LLLL yyyy', 'ru').format(_month));
    final firstDay = DateTime(_month.year, _month.month, 1);
    final daysInMonth = DateTime(_month.year, _month.month + 1, 0).day;
    // Пн = 1 … Вс = 7 → сколько пустых ячеек до первого числа.
    final leading = firstDay.weekday - 1;
    final today = DateTime.now();
    final marked = {
      for (final item in items)
        if (item.endDate.year == _month.year &&
            item.endDate.month == _month.month)
          item.endDate.day: item.renewalStatus,
    };

    return Column(
      children: [
        Row(
          children: [
            IconButton(
              icon: const Icon(Icons.chevron_left,
                  size: 20, color: DsColors.textMuted),
              onPressed: () => setState(
                  () => _month = DateTime(_month.year, _month.month - 1)),
            ),
            Expanded(
              child: Center(
                child: Text(monthTitle, style: DsText.headingSm),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.chevron_right,
                  size: 20, color: DsColors.textMuted),
              onPressed: () => setState(
                  () => _month = DateTime(_month.year, _month.month + 1)),
            ),
          ],
        ),
        const SizedBox(height: 10),
        GridView.count(
          crossAxisCount: 7,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            for (final weekday in const ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'])
              Center(
                child: Text(weekday.toUpperCase(),
                    style: DsText.label.copyWith(color: DsColors.slate400)),
              ),
            for (var i = 0; i < leading; i++) const SizedBox.shrink(),
            for (var day = 1; day <= daysInMonth; day++)
              _dayCell(
                day,
                isToday: today.year == _month.year &&
                    today.month == _month.month &&
                    today.day == day,
                mark: marked[day],
              ),
          ],
        ),
      ],
    );
  }

  Widget _dayCell(int day, {required bool isToday, String? mark}) {
    final markColor = switch (mark) {
      'overdue' => DsColors.dangerFg,
      'due_soon' => DsColors.warningFg,
      'active' => DsColors.indigo500,
      _ => null,
    };
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 30,
          height: 30,
          decoration: isToday
              ? const BoxDecoration(
                  color: DsColors.indigo500, shape: BoxShape.circle)
              : null,
          alignment: Alignment.center,
          child: Text(
            '$day',
            style: DsText.bodySm.copyWith(
              fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
              color: isToday ? Colors.white : DsColors.text,
            ),
          ),
        ),
        SizedBox(
          height: 6,
          child: markColor == null
              ? null
              : Center(
                  child: Container(
                    width: 4,
                    height: 4,
                    decoration: BoxDecoration(
                        color: markColor, shape: BoxShape.circle),
                  ),
                ),
        ),
      ],
    );
  }
}

class _EventRow extends StatelessWidget {
  const _EventRow({required this.item});

  final LeaseCalendarItem item;

  @override
  Widget build(BuildContext context) {
    final (label, tone) = switch (item.renewalStatus) {
      'overdue' => ('Просрочено', StatusTone.danger),
      'due_soon' => ('Скоро', StatusTone.warning),
      _ => ('Активна', StatusTone.success),
    };
    return DsCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        children: [
          SizedBox(
            width: 44,
            child: Column(
              children: [
                Text(
                  DateFormat('dd').format(item.endDate),
                  style: DsText.headingMd.copyWith(fontSize: 17, height: 1),
                ),
                const SizedBox(height: 2),
                Text(
                  DateFormat('MMM', 'ru').format(item.endDate),
                  style: DsText.label.copyWith(fontSize: 10),
                ),
              ],
            ),
          ),
          Container(
            width: 1,
            height: 36,
            color: const Color(0xFFEEF0F4),
            margin: const EdgeInsets.symmetric(horizontal: 12),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.addressFull,
                  style: DsText.bodySm.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text('Окончание аренды', style: DsText.caption),
              ],
            ),
          ),
          const SizedBox(width: 10),
          ToneBadge(label: label, tone: tone),
        ],
      ),
    );
  }
}
