import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../api/client.dart';
import '../api/repositories.dart';
import '../theme/tokens.dart';
import '../widgets/ds.dart';

/// Вход — артборд «04 · Вход». Регистрация отдельного экрана не имеет:
/// аккаунт создаётся вместе с первой заявкой (так устроен бэк).
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.auth});

  final AuthState auth;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final router = GoRouter.of(context);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.auth.login(
        email: _email.text.trim(),
        password: _password.text,
      );
      router.go('/cabinet/requests');
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(error);
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      appBar: AppBar(
        backgroundColor: DsColors.pageBg,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: BackButton(color: DsColors.text, onPressed: context.pop),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                children: [
                  const SizedBox(height: 40),
                  Center(
                    child: Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        gradient: DsColors.logoGradient,
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: DsShadows.raised,
                      ),
                      child: const Icon(Icons.place_outlined,
                          size: 30, color: Colors.white),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Center(
                    child: Text.rich(
                      TextSpan(
                        text: 'uradres',
                        style: DsText.displayMd.copyWith(fontSize: 24),
                        children: const [
                          TextSpan(
                            text: '.net',
                            style: TextStyle(color: DsColors.indigo500),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Center(
                    child:
                        Text('Вход в личный кабинет', style: DsText.muted),
                  ),
                  const SizedBox(height: 36),
                  DsTextField(
                    label: 'E-mail',
                    controller: _email,
                    hint: 'name@company.ru',
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                  ),
                  const SizedBox(height: 14),
                  DsTextField(
                    label: 'Пароль',
                    controller: _password,
                    obscure: true,
                    textInputAction: TextInputAction.done,
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
                        style:
                            DsText.bodySm.copyWith(color: DsColors.dangerFg),
                      ),
                    ),
                  ],
                  const SizedBox(height: 22),
                  DsButton(
                    label: 'Войти',
                    expanded: true,
                    busy: _busy,
                    onPressed: _busy ? null : _submit,
                  ),
                  const SizedBox(height: 12),
                  DsButton(
                    label: 'Оформить первую заявку',
                    kind: DsButtonKind.secondary,
                    expanded: true,
                    onPressed: () => context.go('/'),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 24),
              child: Text(
                'ООО «Юрадрес.Нет» · ИНН 7751397240',
                style: DsText.caption.copyWith(color: DsColors.slate400),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
