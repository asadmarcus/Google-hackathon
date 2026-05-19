import 'package:dio/dio.dart';
import '../config/api_config.dart';
import '../models/prediction.dart';

class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;

  late final Dio _dio;

  ApiService._internal() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
  }

  /// Get 30-day prediction for a zone
  Future<ZonePrediction?> getPrediction(String zoneId) async {
    try {
      final response = await _dio.post('/api/v1/agent3/predict/$zoneId');
      if (response.statusCode == 200) {
        return ZonePrediction.fromJson(response.data);
      }
    } catch (e) {
      print('Prediction error: $e');
    }
    return null;
  }

  /// Trigger data fetch (Agent 2)
  Future<bool> triggerFetch() async {
    try {
      final response = await _dio.post('/api/v1/agent2/fetch');
      return response.statusCode == 200;
    } catch (e) {
      print('Fetch error: $e');
      return false;
    }
  }

  /// Get satellite analysis (Agent 1)
  Future<Map<String, dynamic>?> getSatelliteAnalysis(String zoneId) async {
    try {
      final response = await _dio.get('/api/v1/agent1/latest/$zoneId');
      if (response.statusCode == 200) {
        return response.data;
      }
    } catch (e) {
      print('Satellite error: $e');
    }
    return null;
  }

  /// Trigger satellite analysis for a zone
  Future<Map<String, dynamic>?> analyzeSatellite(String zoneId) async {
    try {
      final response = await _dio.post('/api/v1/agent1/analyze/$zoneId');
      if (response.statusCode == 200) {
        return response.data;
      }
    } catch (e) {
      print('Analyze satellite error: $e');
    }
    return null;
  }

  /// Health check
  Future<bool> isHealthy() async {
    try {
      final response = await _dio.get('/health');
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }
}
