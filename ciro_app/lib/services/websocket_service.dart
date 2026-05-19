import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config/api_config.dart';

/// WebSocket service for real-time signal streaming.
/// Fires push notifications when severity >= 7.
class WebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  Timer? _reconnectTimer;
  final List<Map<String, dynamic>> _recentSignals = [];

  bool get isConnected => _isConnected;
  List<Map<String, dynamic>> get recentSignals => _recentSignals;

  // Callback for high-severity alerts
  void Function(Map<String, dynamic> signal)? onAlert;

  void connect() {
    try {
      _channel = WebSocketChannel.connect(Uri.parse(ApiConfig.wsUrl));
      _isConnected = true;
      notifyListeners();

      _channel!.stream.listen(
        (data) {
          try {
            final signal = json.decode(data) as Map<String, dynamic>;
            _handleSignal(signal);
          } catch (e) {
            debugPrint('WS parse error: $e');
          }
        },
        onDone: () {
          _isConnected = false;
          notifyListeners();
          _scheduleReconnect();
        },
        onError: (error) {
          _isConnected = false;
          notifyListeners();
          _scheduleReconnect();
        },
      );
    } catch (e) {
      debugPrint('WS connect error: $e');
      _scheduleReconnect();
    }
  }

  void _handleSignal(Map<String, dynamic> signal) {
    _recentSignals.insert(0, signal);
    if (_recentSignals.length > 50) _recentSignals.removeLast();
    notifyListeners();

    // Fire alert callback for high severity
    final severity = signal['severity'] ?? 0;
    if (severity >= 7 && onAlert != null) {
      onAlert!(signal);
    }
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      debugPrint('WS reconnecting...');
      connect();
    });
  }

  void disconnect() {
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _isConnected = false;
    notifyListeners();
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
