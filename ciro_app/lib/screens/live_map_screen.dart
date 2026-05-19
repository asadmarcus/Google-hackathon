import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../config/api_config.dart';
import '../theme/ciro_theme.dart';

/// Live Map screen — directs users to the web-based heatmap at localhost:8000/map.
/// The heavy visualization (Google Maps + heatmap layers + 30-day slider)
/// lives on the web. This screen provides the link and instructions.
class LiveMapScreen extends StatelessWidget {
  const LiveMapScreen({super.key});

  Future<void> _openMap() async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/map');
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CiroTheme.bg,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Map illustration
              Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: CiroTheme.surface,
                  border: Border.all(color: CiroTheme.accent.withOpacity(0.3), width: 2),
                  boxShadow: [
                    BoxShadow(
                      color: CiroTheme.accent.withOpacity(0.1),
                      blurRadius: 30,
                      spreadRadius: 5,
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.public_rounded,
                  color: CiroTheme.accent,
                  size: 56,
                ),
              ),
              const SizedBox(height: 28),
              const Text(
                'Live Crisis Map',
                style: TextStyle(
                  color: CiroTheme.textPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                'The interactive heatmap with all 8 zones,\n30-day forecast slider, and real-time\nrisk visualization lives on the web.',
                style: TextStyle(
                  color: CiroTheme.textSecondary,
                  fontSize: 14,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 32),

              // Open map button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _openMap,
                  icon: const Icon(Icons.open_in_browser_rounded, size: 20),
                  label: const Text('Open in Browser'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: CiroTheme.accent,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                    elevation: 0,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              // URL display
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: CiroTheme.surface,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: CiroTheme.border),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.link_rounded, color: CiroTheme.textMuted, size: 16),
                    const SizedBox(width: 8),
                    Text(
                      '${ApiConfig.baseUrl}/map',
                      style: const TextStyle(
                        color: CiroTheme.textSecondary,
                        fontSize: 13,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 32),

              // Features list
              _buildFeature(Icons.layers_rounded, 'Gradient Heatmap', 'Risk intensity across all zones'),
              const SizedBox(height: 10),
              _buildFeature(Icons.tune_rounded, '30-Day Slider', 'See how risk evolves over time'),
              const SizedBox(height: 10),
              _buildFeature(Icons.satellite_alt_rounded, 'Satellite Overlay', 'NDWI & vegetation from Agent 1'),
              const SizedBox(height: 10),
              _buildFeature(Icons.bolt_rounded, 'Real-Time Updates', 'Live WebSocket signal stream'),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFeature(IconData icon, String title, String subtitle) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: CiroTheme.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: CiroTheme.border),
          ),
          child: Icon(icon, color: CiroTheme.accent, size: 18),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
              Text(subtitle, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 11)),
            ],
          ),
        ),
      ],
    );
  }
}
