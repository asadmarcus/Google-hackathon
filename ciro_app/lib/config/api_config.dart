/// CIRO API Configuration
class ApiConfig {
  // Change this to your deployed URL or local IP
  // static const String baseUrl = 'http://localhost:8000'; // Web / desktop
  static const String baseUrl = 'http://10.0.2.2:8000'; // Android emulator
  // static const String baseUrl = 'https://your-cloud-run-url.run.app'; // Production

  static const String wsUrl = 'ws://10.0.2.2:8000/ws/signals';

  // Agent endpoints
  static const String agent1 = '$baseUrl/api/v1/agent1';
  static const String agent2 = '$baseUrl/api/v1/agent2';
  static const String agent3 = '$baseUrl/api/v1/agent3';

  // Specific endpoints
  static String predict(String zoneId) => '$agent3/predict/$zoneId';
  static String signals(String zoneId) => '$agent2/signals/$zoneId';
  static String satellite(String zoneId) => '$agent1/latest/$zoneId';
  static String analyzeZone(String zoneId) => '$agent1/analyze/$zoneId';
  static const String health = '$baseUrl/health';
  static const String fetchAll = '$agent2/fetch';
}
