import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/websocket_service.dart';
import '../models/zone.dart';
import '../theme/ciro_theme.dart';
import 'prediction_screen.dart';

/// Alerts screen — timeline of all alerts received via WebSocket.
/// Each alert shows: zone, severity, trigger, timestamp.
class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CiroTheme.bg,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(),
            Expanded(child: _buildAlertsList(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.notifications_active_rounded, color: CiroTheme.accent, size: 22),
              SizedBox(width: 10),
              Text(
                'Alert Timeline',
                style: TextStyle(
                  color: CiroTheme.textPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'Real-time alerts from severity ≥ 7 signals',
            style: TextStyle(color: CiroTheme.textMuted, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildAlertsList(BuildContext context) {
    final ws = Provider.of<WebSocketService>(context);
    final signals = ws.recentSignals;

    // Filter to only high-severity alerts (≥ 7)
    final alerts = signals.where((s) => (s['severity'] ?? 0) >= 7).toList();

    if (alerts.isEmpty) {
      return _buildEmptyState(ws.isConnected);
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
      itemCount: alerts.length,
      itemBuilder: (context, index) {
        final alert = alerts[index];
        return _AlertCard(
          alert: alert,
          isFirst: index == 0,
          isLast: index == alerts.length - 1,
          onTap: () {
            final zoneId = alert['zone_id'] ?? '';
            final zone = CiroZone.allZones.firstWhere(
              (z) => z.id == zoneId,
              orElse: () => CiroZone.allZones.first,
            );
            Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => PredictionScreen(zone: zone)),
            );
          },
        );
      },
    );
  }

  Widget _buildEmptyState(bool isConnected) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              isConnected
                  ? Icons.shield_outlined
                  : Icons.wifi_off_rounded,
              color: isConnected ? CiroTheme.green : CiroTheme.textMuted,
              size: 56,
            ),
            const SizedBox(height: 16),
            Text(
              isConnected
                  ? 'All Clear'
                  : 'Not Connected',
              style: const TextStyle(
                color: CiroTheme.textPrimary,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              isConnected
                  ? 'No high-severity alerts detected.\nMonitoring all 8 zones in real-time.'
                  : 'WebSocket is offline.\nAlerts will appear here when connected.',
              style: const TextStyle(color: CiroTheme.textMuted, fontSize: 13),
              textAlign: TextAlign.center,
            ),
            if (isConnected) ...[
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  color: CiroTheme.green.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: CiroTheme.green.withOpacity(0.2)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: CiroTheme.green,
                      ),
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'Live monitoring active',
                      style: TextStyle(color: CiroTheme.green, fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Individual alert card with timeline connector
class _AlertCard extends StatelessWidget {
  final Map<String, dynamic> alert;
  final bool isFirst;
  final bool isLast;
  final VoidCallback onTap;

  const _AlertCard({
    required this.alert,
    required this.isFirst,
    required this.isLast,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final severity = alert['severity'] ?? 0;
    final zoneName = alert['zone_name'] ?? 'Unknown Zone';
    final zoneId = alert['zone_id'] ?? '';
    final signalType = alert['signal_type'] ?? 'alert';
    final timestamp = alert['timestamp'] ?? '';
    final isCritical = severity >= 8;
    final color = isCritical ? CiroTheme.red : CiroTheme.yellow;

    // Find province from zone data
    final zone = CiroZone.allZones.firstWhere(
      (z) => z.id == zoneId,
      orElse: () => CiroZone.allZones.first,
    );

    return GestureDetector(
      onTap: onTap,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Timeline connector
            SizedBox(
              width: 32,
              child: Column(
                children: [
                  // Line above
                  if (!isFirst)
                    Expanded(child: Container(width: 2, color: CiroTheme.border))
                  else
                    const Expanded(child: SizedBox()),
                  // Dot
                  Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color,
                      boxShadow: [
                        BoxShadow(color: color.withOpacity(0.4), blurRadius: 6),
                      ],
                    ),
                  ),
                  // Line below
                  if (!isLast)
                    Expanded(child: Container(width: 2, color: CiroTheme.border))
                  else
                    const Expanded(child: SizedBox()),
                ],
              ),
            ),
            const SizedBox(width: 8),
            // Card content
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: CiroTheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isCritical
                        ? CiroTheme.red.withOpacity(0.3)
                        : CiroTheme.border,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Header: zone name + severity badge
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            zoneName,
                            style: const TextStyle(
                              color: CiroTheme.textPrimary,
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: color.withOpacity(0.12),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            'SEV $severity',
                            style: TextStyle(
                              color: color,
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      zone.province,
                      style: const TextStyle(color: CiroTheme.textMuted, fontSize: 11),
                    ),
                    const SizedBox(height: 10),
                    // Trigger info
                    Row(
                      children: [
                        Icon(
                          _triggerIcon(signalType),
                          color: CiroTheme.textSecondary,
                          size: 14,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          _triggerLabel(signalType),
                          style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12),
                        ),
                      ],
                    ),
                    if (timestamp.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(
                        timestamp,
                        style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10),
                      ),
                    ],
                    const SizedBox(height: 8),
                    // Tap hint
                    Row(
                      children: const [
                        Text(
                          'View 30-day forecast →',
                          style: TextStyle(color: CiroTheme.accent, fontSize: 11, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  IconData _triggerIcon(String type) {
    switch (type.toLowerCase()) {
      case 'flood': return Icons.water_rounded;
      case 'heat': return Icons.thermostat_rounded;
      case 'rainfall': return Icons.grain_rounded;
      case 'discharge': return Icons.waves_rounded;
      default: return Icons.warning_rounded;
    }
  }

  String _triggerLabel(String type) {
    switch (type.toLowerCase()) {
      case 'flood': return 'Flood risk threshold exceeded';
      case 'heat': return 'Extreme heat detected';
      case 'rainfall': return 'Heavy rainfall warning';
      case 'discharge': return 'River discharge anomaly';
      default: return 'Alert: $type';
    }
  }
}
