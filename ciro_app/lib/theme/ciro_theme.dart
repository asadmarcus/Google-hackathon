import 'package:flutter/material.dart';

class CiroTheme {
  // Brand colors (matching web dashboard)
  static const Color bg = Color(0xFF0F1419);
  static const Color surface = Color(0xFF1A2332);
  static const Color surfaceHover = Color(0xFF1E2A3A);
  static const Color border = Color(0xFF2D3A4A);
  static const Color textPrimary = Color(0xFFE8EAED);
  static const Color textSecondary = Color(0xFF9AA0A6);
  static const Color textMuted = Color(0xFF5F6368);
  static const Color accent = Color(0xFFF97316);
  static const Color blue = Color(0xFF3B82F6);
  static const Color green = Color(0xFF22C55E);
  static const Color red = Color(0xFFEF4444);
  static const Color yellow = Color(0xFFEAB308);
  static const Color purple = Color(0xFFA855F7);

  // Alert level colors
  static Color alertColor(String level) {
    switch (level.toUpperCase()) {
      case 'CRITICAL': return red;
      case 'HIGH': return red.withOpacity(0.8);
      case 'MODERATE': return yellow;
      case 'LOW': return green;
      default: return textMuted;
    }
  }

  // Severity to color (1-10)
  static Color severityColor(double risk) {
    if (risk >= 0.7) return red;
    if (risk >= 0.4) return yellow;
    if (risk >= 0.2) return accent;
    return green;
  }

  // Map marker color based on max risk
  static Color markerColor(double maxRisk) {
    if (maxRisk >= 0.7) return red;
    if (maxRisk >= 0.4) return yellow;
    return green;
  }

  static ThemeData get darkTheme => ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: bg,
    primaryColor: accent,
    colorScheme: const ColorScheme.dark(
      primary: accent,
      secondary: blue,
      surface: surface,
      error: red,
    ),
    cardColor: surface,
    dividerColor: border,
    appBarTheme: const AppBarTheme(
      backgroundColor: surface,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: textPrimary,
        fontSize: 18,
        fontWeight: FontWeight.w700,
      ),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: surface,
      selectedItemColor: accent,
      unselectedItemColor: textMuted,
    ),
    textTheme: const TextTheme(
      headlineLarge: TextStyle(color: textPrimary, fontWeight: FontWeight.w700),
      headlineMedium: TextStyle(color: textPrimary, fontWeight: FontWeight.w600),
      bodyLarge: TextStyle(color: textPrimary),
      bodyMedium: TextStyle(color: textSecondary),
      bodySmall: TextStyle(color: textMuted),
    ),
  );
}
