import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../api/client.dart';
import '../api/repositories.dart';
import '../models/address.dart';
import '../theme/tokens.dart';
import '../widgets/ds.dart';

/// Форма заявки — артборд «03 · Заявка».
///
/// Отличия от макета, продиктованные API (POST /marketplace/applications
/// создаёт аккаунт клиента одним действием):
///  - есть поле «Пароль» (мин. 8 символов);
///  - для «Смены адреса действующей компании» обязателен ИНН.
class ApplicationScreen extends StatefulWidget {
  const ApplicationScreen({
    super.key,
    required this.catalog,
    required this.auth,
    required this.address,
  });

  final CatalogRepository catalog;
  final AuthState auth;
  final PublicAddress address;

  @override
  State<ApplicationScreen> createState() => _ApplicationScreenState();
}

class _ApplicationScreenState extends State<ApplicationScreen> {
  final _company = TextEditingController();
  final _contact = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _inn = TextEditingController();

  int _termMonths = 11;
  bool _isAddressChange = false;
  bool _withMail = false;
  bool _consent = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    for (final controller in [_company, _contact, _phone, _email, _password, _inn]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      await widget.catalog.createApplication(
        addressId: widget.address.id,
        companyName: _company.text.trim(),
        contactName: _contact.text.trim(),
        contactEmail: _email.text.trim(),
        contactPhone: _phone.text.trim(),
        password: _password.text,
        termMonths: _termMonths,
        hasCorrespondence: _withMail,
        isAddressChange: _isAddressChange,
        clientInn: _inn.text.trim().isEmpty ? null : _inn.text.trim(),
      );
      // Аккаунт создан вместе с заявкой — сразу получаем bearer-сессию
      // и уводим в кабинет.
      await widget.auth.login(
        email: _email.text.trim(),
        password: _password.text,
      );
      messenger.showSnackBar(const SnackBar(
        content: Text('Заявка отправлена. Собственник подтвердит готовность '
            'выдать документы — статус появится в кабинете.'),
      ));
      router.go('/cabinet/requests');
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(error);
        _busy = false;
      });
    }
  }

  bool get _canSubmit =>
      !_busy &&
      _consent &&
      _contact.text.trim().isNotEmpty &&
      _email.text.trim().isNotEmpty &&
      _password.text.length >= 8 &&
      (_isAddressChange
          ? _inn.text.trim().isNotEmpty
          : _company.text.trim().isNotEmpty);

  @override
  Widget build(BuildContext context) {
    final address = widget.address;
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      appBar: AppBar(
        backgroundColor: DsColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: BackButton(color: DsColors.text, onPressed: context.pop),
        title: Text('Оформление заявки', style: DsText.headingMd),
        shape: const Border(bottom: BorderSide(color: DsColors.borderSoft)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          DsCard(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: SizedBox(
                    width: 56,
                    height: 56,
                    child: address.mainPhotoUrl != null
                        ? Image.network(
                            absoluteUrl(address.mainPhotoUrl!),
                            fit: BoxFit.cover,
                            errorBuilder: (_, _, _) => InitialsTile(
                              initials: address.initials,
                              fontSize: 18,
                            ),
                          )
                        : InitialsTile(
                            initials: address.initials,
                            fontSize: 18,
                          ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        address.fullAddress,
                        style: DsText.bodySm
                            .copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        '$_termMonths мес. · '
                        '${formatRub(address.priceFor(_termMonths))}',
                        style: DsText.caption,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          if (!_isAddressChange) ...[
            DsTextField(
              label: 'Название компании',
              controller: _company,
              hint: 'ООО «Ромашка»',
            ),
            const SizedBox(height: 16),
          ],
          DsTextField(
            label: 'Контактное лицо',
            controller: _contact,
            hint: 'Имя и фамилия',
          ),
          const SizedBox(height: 16),
          DsTextField(
            label: 'Телефон',
            controller: _phone,
            hint: '+7',
            keyboardType: TextInputType.phone,
          ),
          const SizedBox(height: 16),
          DsTextField(
            label: 'E-mail',
            controller: _email,
            hint: 'name@company.ru',
            keyboardType: TextInputType.emailAddress,
          ),
          const SizedBox(height: 16),
          DsTextField(
            label: 'Пароль для кабинета',
            controller: _password,
            hint: 'Минимум 8 символов',
            obscure: true,
          ),
          const SizedBox(height: 20),
          const SectionLabel('Срок аренды'),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: DsSegmented(
              options: const ['6 мес.', '11 мес.'],
              selectedIndex: _termMonths == 6 ? 0 : 1,
              onChanged: (index) =>
                  setState(() => _termMonths = index == 0 ? 6 : 11),
            ),
          ),
          const SizedBox(height: 20),
          const SectionLabel('Тип заявки'),
          const SizedBox(height: 8),
          _radio(
            label: 'Регистрация новой компании',
            selected: !_isAddressChange,
            onTap: () => setState(() => _isAddressChange = false),
          ),
          const SizedBox(height: 8),
          _radio(
            label: 'Смена адреса действующей компании',
            selected: _isAddressChange,
            onTap: () => setState(() => _isAddressChange = true),
          ),
          if (_isAddressChange) ...[
            const SizedBox(height: 16),
            DsTextField(
              label: 'ИНН компании',
              controller: _inn,
              hint: '10 цифр',
              keyboardType: TextInputType.number,
            ),
          ],
          if (widget.address.correspondencePrice != null) ...[
            const SizedBox(height: 20),
            _checkboxRow(
              checked: _withMail,
              onTap: () => setState(() => _withMail = !_withMail),
              child: Text(
                '+ почта ${formatRub(widget.address.correspondencePrice!)}/мес',
                style: DsText.bodySm,
              ),
            ),
          ],
          const SizedBox(height: 18),
          _checkboxRow(
            checked: _consent,
            onTap: () => setState(() => _consent = !_consent),
            child: Text.rich(
              TextSpan(
                text: 'Согласен на ',
                style: DsText.bodySm.copyWith(color: DsColors.slate700),
                children: [
                  TextSpan(
                    text: 'обработку персональных данных',
                    style:
                        DsText.bodySm.copyWith(color: DsColors.indigo500),
                  ),
                ],
              ),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: DsColors.dangerBg,
                borderRadius: BorderRadius.circular(DsRadii.card),
              ),
              child: Text(
                _error!,
                style: DsText.bodySm.copyWith(color: DsColors.dangerFg),
              ),
            ),
          ],
          const SizedBox(height: 18),
          DsButton(
            label: 'Отправить заявку',
            expanded: true,
            busy: _busy,
            onPressed: _canSubmit ? _submit : null,
          ),
          const SizedBox(height: 12),
          Text(
            'Собственник подтвердит готовность выдать документы — '
            'статус заявки появится в личном кабинете.',
            style: DsText.caption,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _radio({
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        decoration: BoxDecoration(
          color: DsColors.surface,
          borderRadius: BorderRadius.circular(DsRadii.card),
          border: Border.all(
            color: selected ? DsColors.indigo500 : DsColors.slate200,
          ),
          boxShadow: selected
              ? const [
                  BoxShadow(color: Color(0x1F5B5BD6), spreadRadius: 3),
                ]
              : null,
        ),
        child: Row(
          children: [
            Container(
              width: 18,
              height: 18,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: DsColors.surface,
                border: Border.all(
                  color: selected ? DsColors.indigo500 : DsColors.slate300,
                  width: selected ? 5.5 : 1.5,
                ),
              ),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Text(
                label,
                style: DsText.body.copyWith(
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _checkboxRow({
    required bool checked,
    required VoidCallback onTap,
    required Widget child,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 17,
            height: 17,
            margin: const EdgeInsets.only(top: 1),
            decoration: BoxDecoration(
              color: checked ? DsColors.indigo500 : DsColors.surface,
              borderRadius: BorderRadius.circular(4),
              border: checked ? null : Border.all(color: DsColors.slate300),
            ),
            child: checked
                ? const Icon(Icons.check, size: 12, color: Colors.white)
                : null,
          ),
          const SizedBox(width: 10),
          Expanded(child: child),
        ],
      ),
    );
  }
}
