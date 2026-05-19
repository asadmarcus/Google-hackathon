# CIRO Flutter App

> Crisis Intelligence & Response Orchestrator — Mobile Client

## Features

- **Full-screen map** with 8 Pakistan urban zones (Google Maps, dark theme)
- **Color-coded markers**: 🟢 Low → 🟡 Moderate → 🔴 High flood risk
- **30-day forecast** — tap any zone for interactive bar chart with daily flood + heat risk
- **Day detail** — tap any bar for temp, rain, humidity, alert level, data source
- **Push notifications** — automatic alert when any zone hits severity ≥ 7
- **WebSocket live** — real-time signal updates, auto-reconnect
- **Notification tap** — opens the affected zone's forecast directly

## Setup

```bash
cd ciro_app

# Create the Flutter project shell (if not already)
flutter create . --org com.ciro --project-name ciro_app

# Get packages
flutter pub get
```

### Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable "Maps SDK for Android" and "Maps SDK for iOS"
3. Create an API key
4. Add to `android/app/src/main/AndroidManifest.xml`:
   ```xml
   <meta-data android:name="com.google.android.geo.API_KEY" android:value="YOUR_KEY"/>
   ```
5. For iOS, add to `ios/Runner/AppDelegate.swift`:
   ```swift
   GMSServices.provideAPIKey("YOUR_KEY")
   ```

### Backend URL

Edit `lib/config/api_config.dart`:
- Emulator: `http://10.0.2.2:8000`
- Physical device on same WiFi: `http://YOUR_PC_IP:8000`
- Production: Your Cloud Run URL

## Run

```bash
# Start backend first
cd ../backend && uvicorn main:app --host 0.0.0.0 --port 8000

# Run Flutter app
cd ../ciro_app && flutter run
```

## Architecture

```
lib/
├── main.dart              # Entry point, WebSocket + notifications setup
├── config/api_config.dart # Backend URL configuration
├── models/
│   ├── zone.dart          # 8 Pakistan zones with lat/lng
│   └── prediction.dart    # 30-day forecast models
├── services/
│   ├── api_service.dart   # Dio HTTP client (Agent 1/2/3 endpoints)
│   ├── websocket_service.dart  # Live signal stream + alert callback
│   └── notification_service.dart  # Local push notifications
├── screens/
│   ├── map_screen.dart    # Full-screen Google Map (home)
│   └── prediction_screen.dart  # 30-day forecast with chart
└── theme/
    └── ciro_theme.dart    # Dark theme matching web dashboard
```

## Flow

```
App opens → Map with 8 pins (color = risk level)
         → Tap pin → 30-day forecast (chart + details)
         → WebSocket receives severity ≥ 7 → Push notification
         → Tap notification → Opens that zone's forecast
```
