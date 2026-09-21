import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../api/client.dart';
import '../../api/repositories.dart';
import '../../models/application.dart';
import '../../theme/tokens.dart';
import '../../widgets/ds.dart';

/// Заявки — вкладка кабинета по умолчанию, артборд «05 · Заявки».
class RequestsScreen extends StatefulWidget {
  const RequestsScreen({super.key, required this.cabinet, required this.auth});

  final CabinetRepository cabinet;
  final AuthState auth;

  @override
  State<RequestsScreen> createState() => _RequestsScreenState();
}

class _RequestsScreenState extends State<RequestsScreen> {
  List<ClientApplication>? _applications;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final applications = await widget.cabinet.applications();
      if (!mounted) return;
      setState(() => _applications = applications);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final applications = _applications;
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
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Заявки', style: DsText.displayMd),
                        if (applications != null) ...[
                          const SizedBox(height: 3),
                          Text(
                            'Всего заявок: ${applications.length}',
                            style: DsText.muted,
                          ),
                        ],
                      ],
                    ),
                  ),
                  GestureDetector(
                    onTap: () => _profileSheet(context),
                    child: InitialsAvatar(
                      initials: widget.auth.user?.initials ?? '·',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              if (_error != null)
                ListState.error(apiErrorMessage(_error!), onRetry: _load)
              else if (applications == null)
                const ListState.loading()
              else if (applications.isEmpty)
                const ListState.empty(
                    'Заявок пока нет. Выберите адрес в каталоге — '
                    'заявка появится здесь.')
              else
                for (final application in applications)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _ApplicationCard(
                      application: application,
                      // После экрана заявки перечитываем список: там могли
                      // оплатить, и статус в карточке устарел бы.
                      onOpen: () async {
                        await context.push(
                          '/cabinet/requests/${application.id}',
                          extra: application,
                        );
                        if (mounted) _load();
                      },
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }

  void _profileSheet(BuildContext context) {
    final user = widget.auth.user;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: DsColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(DsRadii.modal)),
      ),
      builder: (sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(user?.fullName ?? '', style: DsText.headingMd),
              const SizedBox(height: 4),
              Row(
                children: [
                  Text(user?.email ?? '', style: DsText.muted),
                  if (user != null && !user.emailVerified) ...[
                    const SizedBox(width: 8),
                    const ToneBadge(
                        label: 'Не подтверждён', tone: StatusTone.warning),
                  ],
                ],
              ),
              const SizedBox(height: 20),
              DsButton(
                label: 'Выйти',
                kind: DsButtonKind.secondary,
                expanded: true,
                onPressed: () async {
                  Navigator.of(sheetContext).pop();
                  await widget.auth.logout();
                },
              ),
              const SizedBox(height: 12),
              Center(
                child: Text(
                  'ООО «Юрадрес.Нет» · ИНН 7751397240',
                  style: DsText.caption.copyWith(color: DsColors.slate400),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ApplicationCard extends StatelessWidget {
  const _ApplicationCard({required this.application, required this.onOpen});

  final ClientApplication application;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final date = DateFormat('dd.MM.yyyy').format(application.createdAt);
    return DsCard(
      onTap: onOpen,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  application.fullAddress,
                  style: DsText.bodySm.copyWith(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              StatusBadge(status: application.status),
            ],
          ),
          if (application.companyName != null) ...[
            const SizedBox(height: 5),
            Text(application.companyName!, style: DsText.muted),
          ],
          const SizedBox(height: 10),
          const Divider(height: 1, color: Color(0xFFEEF0F4)),
          const SizedBox(height: 10),
          Row(
            children: [
              Text(date, style: DsText.caption),
              const Spacer(),
              Text(
                formatRub(application.priceTotal),
                style: DsText.headingSm.copyWith(fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
