import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'theme/ciro_theme.dart';
import 'screens/home_screen.dart';
import 'screens/live_map_screen.dart';
import 'screens/agents_screen.dart';
import 'screens/prediction_screen.dart';
import 'services/websocket_service.dart';
import 'services/notification_service.dart';
import 'models/zone.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService().initialize();
  runApp(const CiroApp());
}

class CiroApp extends StatelessWidget {
  const CiroApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => WebSocketService(),
      child: MaterialApp(
        title: 'CIRO',
        debugShowCheckedModeBanner: false,
        theme: CiroTheme.darkTheme,
        home: const AppShell(),
      ),
    );
  }
}

/// Main app shell with bottom navigation: Home, Alerts, Live Map
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _currentIndex = 0;

  final List<Widget> _screens = const [
    HomeScreen(),
    AgentsScreen(),
    LiveMapScreen(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _setupWebSocket();
    });
  }

  void _setupWebSocket() {
    final ws = Provider.of<WebSocketService>(context, listen: false);
    ws.connect();

    ws.onAlert = (signal) {
      final zoneId = signal['zone_id'] ?? '';
      final zoneName = signal['zone_name'] ?? 'Unknown';
      final severity = signal['severity'] ?? 0;
      final type = signal['signal_type'] ?? 'alert';

      NotificationService().showAlert(
        zoneId: zoneId,
        zoneName: zoneName,
        severity: severity,
        message: 'Severity $severity — $type detected. Tap for 30-day forecast.',
      );
    };

    NotificationService().onNotificationTap = (zoneId) {
      final zone = CiroZone.allZones.firstWhere(
        (z) => z.id == zoneId,
        orElse: () => CiroZone.allZones.first,
      );
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => PredictionScreen(zone: zone)),
      );
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(
            top: BorderSide(color: CiroTheme.border, width: 0.5),
          ),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) => setState(() => _currentIndex = index),
          backgroundColor: CiroTheme.surface,
          selectedItemColor: CiroTheme.accent,
          unselectedItemColor: CiroTheme.textMuted,
          type: BottomNavigationBarType.fixed,
          selectedFontSize: 11,
          unselectedFontSize: 11,
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.home_rounded),
              label: 'Home',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.psychology_rounded),
              label: 'AI Agents',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.map_rounded),
              label: 'Live Map',
            ),
          ],
        ),
      ),
    );
  }
}
