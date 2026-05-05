# OKRA Modern Workbench

The modern workbench is a React + Tauri desktop UI that keeps the existing Python research backend.

## Start

```powershell
.\run_desktop_app.ps1
```

The launcher starts or opens:

- Python local API: `http://127.0.0.1:8765`
- Tauri workbench executable when Rust/Cargo is available
- React dev workbench at `http://127.0.0.1:5173` as a fallback when Cargo is unavailable

## Frontend

```powershell
cd F:\okra_assistant\frontend
npm install
npm run dev
```

Tauri config is included under `frontend/src-tauri`. Building or running the native Tauri app requires Rust and Cargo.
Use `npm run tauri:check` to validate the Rust/Tauri project without creating an installer.
`npm run tauri -- build` may download NSIS/WiX bundler binaries on Windows.

## API

```powershell
python F:\okra_assistant\app\web_api.py --home F:\okra_assistant
```

Available endpoints:

- `GET /api/dates`
- `GET /api/snapshot?date=YYYY-MM-DD`
- `POST /api/run/daily`
- `POST /api/run/realtime`
- `POST /api/copilot/explain`
