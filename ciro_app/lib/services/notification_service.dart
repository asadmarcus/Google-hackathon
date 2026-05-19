import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'dart:ui' show Color;

class NotificationService {
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  
  // Store zone id for notification tap handling
  String? _lastTappedZone;
  String? get lastTappedZone => _lastTappedZone;
  void Function(String zoneId)? onNotificationTap;

  Future<void> initialize() async {
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );

    await _plugin.initialize(
      const InitializationSettings(android: androidSettings, iOS: iosSettings),
      onDidReceiveNotificationResponse: (response) {
        final zoneId = response.payload;
        if (zoneId != null && onNotificationTap != null) {
          _lastTappedZone = zoneId;
          onNotificationTap!(zoneId);
        }
      },
    );
  }

  /// Show a crisis alert notification
  Future<void> showAlert({
    required String zoneId,
    required String zoneName,
    required int severity,
    required String message,
  }) async {
    final String title = severity >= 8
        ? '🚨 CRITICAL: $zoneName'
        : '⚠️ HIGH RISK: $zoneName';

    await _plugin.show(
      zoneId.hashCode, // unique id per zone
      title,
      message,
      NotificationDetails(
        android: AndroidNotificationDetails(
          'ciro_alerts',
          'Crisis Alerts',
          channelDescription: 'CIRO flood and heatwave alerts',
          importance: Importance.max,
          priority: Priority.high,
          color: severity >= 8 
              ? const Color(0xFFEF4444) 
              : const Color(0xFFEAB308),
        ),
        iOS: const DarwinNotificationDetails(
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
      ),
      payload: zoneId,
    );
  }
}
