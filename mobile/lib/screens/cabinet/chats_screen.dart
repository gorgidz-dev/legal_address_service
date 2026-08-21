import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../api/client.dart';
import '../../api/repositories.dart';
import '../../models/misc.dart';
import '../../theme/tokens.dart';
import '../../widgets/ds.dart';

/// Чаты — артборд «08 · Чат»: список диалогов, по тапу — переписка.
///
/// В скелете чтение по REST (GET /chats, /chats/{id}/messages); живой
/// WebSocket и отправка сообщений — следующий шаг.
class ChatsScreen extends StatefulWidget {
  const ChatsScreen({super.key, required this.cabinet, required this.auth});

  final CabinetRepository cabinet;
  final AuthState auth;

  @override
  State<ChatsScreen> createState() => _ChatsScreenState();
}

class _ChatsScreenState extends State<ChatsScreen> {
  List<ChatSummary>? _chats;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final chats = await widget.cabinet.chats();
      if (!mounted) return;
      setState(() => _chats = chats);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final chats = _chats;
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
                  Expanded(child: Text('Чаты', style: DsText.displayMd)),
                  InitialsAvatar(
                      initials: widget.auth.user?.initials ?? '·'),
                ],
              ),
              const SizedBox(height: 16),
              if (_error != null)
                ListState.error(apiErrorMessage(_error!), onRetry: _load)
              else if (chats == null)
                const ListState.loading()
              else if (chats.isEmpty)
                const ListState.empty('Пока нет сообщений.')
              else
                for (final chat in chats)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _ChatRow(
                      chat: chat,
                      onOpen: () => _openChat(chat),
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }

  void _openChat(ChatSummary chat) {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => _ChatThreadScreen(chat: chat, cabinet: widget.cabinet),
    ));
  }
}

class _ChatRow extends StatelessWidget {
  const _ChatRow({required this.chat, required this.onOpen});

  final ChatSummary chat;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return DsCard(
      onTap: onOpen,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              gradient: chat.unreadCount > 0 ? DsColors.fallbackGradient : null,
              color: chat.unreadCount > 0 ? null : DsColors.brandBg,
              borderRadius: BorderRadius.circular(10),
            ),
            alignment: Alignment.center,
            child: Icon(
              Icons.chat_bubble_outline,
              size: 18,
              color:
                  chat.unreadCount > 0 ? Colors.white : DsColors.brandFg,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  chat.addressFull,
                  style: DsText.bodySm.copyWith(fontWeight: FontWeight.w700),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  chat.providerName,
                  style: DsText.caption,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (chat.lastMessageAt != null)
                Text(
                  _when(chat.lastMessageAt!),
                  style: DsText.caption.copyWith(color: DsColors.slate400),
                ),
              if (chat.unreadCount > 0) ...[
                const SizedBox(height: 5),
                Container(
                  constraints: const BoxConstraints(minWidth: 18),
                  height: 18,
                  padding: const EdgeInsets.symmetric(horizontal: 5),
                  decoration: BoxDecoration(
                    color: DsColors.indigo500,
                    borderRadius: BorderRadius.circular(DsRadii.pill),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    '${chat.unreadCount}',
                    style: DsText.label
                        .copyWith(color: Colors.white, letterSpacing: 0),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  String _when(DateTime time) {
    final local = time.toLocal();
    final now = DateTime.now();
    final isToday = local.year == now.year &&
        local.month == now.month &&
        local.day == now.day;
    if (isToday) return DateFormat('HH:mm').format(local);
    return DateFormat('dd.MM').format(local);
  }
}

/// Открытая переписка. Композер выключен: отправка приедет вместе с WS.
class _ChatThreadScreen extends StatefulWidget {
  const _ChatThreadScreen({required this.chat, required this.cabinet});

  final ChatSummary chat;
  final CabinetRepository cabinet;

  @override
  State<_ChatThreadScreen> createState() => _ChatThreadScreenState();
}

class _ChatThreadScreenState extends State<_ChatThreadScreen> {
  List<ChatMessage>? _messages;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final messages = await widget.cabinet.messages(widget.chat.id);
      if (!mounted) return;
      setState(() => _messages = messages);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final messages = _messages;
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      appBar: AppBar(
        backgroundColor: DsColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: BackButton(
            color: DsColors.text,
            onPressed: () => Navigator.of(context).pop()),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.chat.addressFull,
              style: DsText.bodySm.copyWith(fontWeight: FontWeight.w700),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            Text(widget.chat.providerName, style: DsText.caption),
          ],
        ),
        shape: const Border(bottom: BorderSide(color: DsColors.borderSoft)),
      ),
      body: Column(
        children: [
          Expanded(
            child: _error != null
                ? ListState.error(apiErrorMessage(_error!), onRetry: _load)
                : messages == null
                    ? const ListState.loading()
                    : messages.isEmpty
                        ? const ListState.empty('Сообщений пока нет.')
                        : ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: messages.length,
                            itemBuilder: (_, index) =>
                                _bubble(messages[index]),
                          ),
          ),
          Container(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
            decoration: const BoxDecoration(
              color: DsColors.surface,
              border: Border(top: BorderSide(color: DsColors.borderSoft)),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 11),
                      decoration: BoxDecoration(
                        color: DsColors.pageBg,
                        borderRadius: BorderRadius.circular(DsRadii.pill),
                        border: Border.all(color: DsColors.slate200),
                      ),
                      child: Text(
                        'Отправка сообщений появится в следующей версии',
                        style:
                            DsText.bodySm.copyWith(color: DsColors.slate400),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Container(
                    width: 40,
                    height: 40,
                    decoration: const BoxDecoration(
                      color: DsColors.slate200,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.send_outlined,
                        size: 18, color: Colors.white),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _bubble(ChatMessage message) {
    final mine = message.isMine;
    final sideLabel = switch (message.authorSide) {
      'owner' => 'Собственник',
      'staff' => 'Поддержка',
      _ => message.authorName,
    };
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 300),
        child: Column(
          crossAxisAlignment:
              mine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            if (!mine)
              Padding(
                padding: const EdgeInsets.only(left: 4, bottom: 3),
                child: Text(sideLabel,
                    style:
                        DsText.label.copyWith(letterSpacing: 0)),
              ),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
              decoration: BoxDecoration(
                color: mine ? DsColors.brandBg : DsColors.slate100,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(14),
                  topRight: const Radius.circular(14),
                  bottomLeft: Radius.circular(mine ? 14 : 4),
                  bottomRight: Radius.circular(mine ? 4 : 14),
                ),
              ),
              child: Text(message.body, style: DsText.body),
            ),
            for (final attachment in message.attachments)
              Container(
                margin: const EdgeInsets.only(top: 4),
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                decoration: BoxDecoration(
                  color: mine ? DsColors.brandBg : DsColors.slate100,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.attach_file,
                        size: 15, color: DsColors.indigo500),
                    const SizedBox(width: 7),
                    Flexible(
                      child: Text(
                        attachment.sizeBytes == null
                            ? attachment.filename
                            : '${attachment.filename} · '
                                '${(attachment.sizeBytes! / 1024).round()} КБ',
                        style: DsText.bodySm
                            .copyWith(fontWeight: FontWeight.w600),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            Padding(
              padding: const EdgeInsets.only(top: 3, bottom: 12),
              child: Text(
                DateFormat('HH:mm').format(message.createdAt.toLocal()),
                style: DsText.caption.copyWith(color: DsColors.slate400),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
