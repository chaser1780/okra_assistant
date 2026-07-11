use std::io::{Read, Write};
use std::net::TcpStream;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use tauri::{AppHandle, Manager};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct ApiProcess(Mutex<Option<Child>>);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum DesktopMode {
    Local,
    Remote,
}

impl DesktopMode {
    fn as_str(self) -> &'static str {
        match self {
            Self::Local => "local",
            Self::Remote => "remote",
        }
    }
}

fn parse_desktop_mode(value: Option<&str>) -> DesktopMode {
    match value
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "remote" => DesktopMode::Remote,
        _ => DesktopMode::Local,
    }
}

fn desktop_mode() -> DesktopMode {
    parse_desktop_mode(std::env::var("OKRA_DESKTOP_MODE").ok().as_deref())
}

fn env_value(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn local_api_host() -> String {
    env_value("OKRA_LOCAL_API_HOST").unwrap_or_else(|| "127.0.0.1".to_string())
}

fn local_api_port() -> u16 {
    env_value("OKRA_LOCAL_API_PORT")
        .and_then(|value| value.parse().ok())
        .unwrap_or(8765)
}

fn local_api_base() -> (String, String) {
    if let Some(value) = env_value("OKRA_LOCAL_API_BASE") {
        return (value, "OKRA_LOCAL_API_BASE".to_string());
    }
    (
        format!("http://{}:{}", local_api_host(), local_api_port()),
        "default".to_string(),
    )
}

fn remote_api_base() -> (String, String) {
    if let Some(value) = env_value("OKRA_REMOTE_API_BASE") {
        return (value, "OKRA_REMOTE_API_BASE".to_string());
    }
    if let Some(value) = env_value("VITE_OKRA_API_BASE") {
        return (value, "VITE_OKRA_API_BASE".to_string());
    }
    if let Some(value) = option_env!("VITE_OKRA_API_BASE")
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return (
            value.to_string(),
            "build-time VITE_OKRA_API_BASE".to_string(),
        );
    }
    (String::new(), "unconfigured".to_string())
}

fn diagnostic_api_base(value: &str) -> String {
    let without_fragment = value.split(['?', '#']).next().unwrap_or_default();
    if let Some((scheme, remainder)) = without_fragment.split_once("://") {
        let safe_remainder = remainder
            .rsplit_once('@')
            .map(|(_, host)| host)
            .unwrap_or(remainder);
        return format!("{scheme}://{safe_remainder}");
    }
    without_fragment.to_string()
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopRuntimeConfig {
    mode: String,
    api_base: String,
    diagnostic_api_base: String,
    configured: bool,
    source: String,
}

fn runtime_config() -> DesktopRuntimeConfig {
    let mode = desktop_mode();
    let (api_base, source) = match mode {
        DesktopMode::Local => local_api_base(),
        DesktopMode::Remote => remote_api_base(),
    };
    DesktopRuntimeConfig {
        mode: mode.as_str().to_string(),
        diagnostic_api_base: diagnostic_api_base(&api_base),
        configured: mode == DesktopMode::Local || !api_base.is_empty(),
        api_base,
        source,
    }
}

#[tauri::command]
fn desktop_runtime_config() -> DesktopRuntimeConfig {
    runtime_config()
}

fn api_is_available() -> bool {
    let address = format!("{}:{}", local_api_host(), local_api_port());
    let Ok(socket_address) = address.parse() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&socket_address, Duration::from_millis(250))
    else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    if stream
        .write_all(
            format!("GET /api/health HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n\r\n")
                .as_bytes(),
        )
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    response.contains("\"app\":\"okra-assistant\"")
        || response.contains("\"app\": \"okra-assistant\"")
}

fn project_root(app: &AppHandle) -> PathBuf {
    if let Ok(home) = std::env::var("FUND_AGENT_HOME") {
        let path = PathBuf::from(home);
        if path.join("app").join("web_api.py").exists() {
            return path;
        }
    }

    if let Ok(current) = std::env::current_dir() {
        if current.join("app").join("web_api.py").exists() {
            return current;
        }
        if let Some(parent) = current.parent() {
            if parent.join("app").join("web_api.py").exists() {
                return parent.to_path_buf();
            }
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors() {
            if ancestor.join("app").join("web_api.py").exists() {
                return ancestor.to_path_buf();
            }
        }
    }

    app.path()
        .home_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("okra_assistant")
}

fn python_command(root: &Path) -> (String, Vec<String>) {
    if let Ok(exe) = std::env::var("OKRA_PYTHON_EXE") {
        if !exe.trim().is_empty() {
            return (windows_gui_python(exe), Vec::new());
        }
    }

    let project_toml = root.join("project.toml");
    if let Ok(text) = std::fs::read_to_string(project_toml) {
        for line in text.lines() {
            let trimmed = line.trim();
            if let Some(value) = trimmed.strip_prefix("python_executable") {
                if let Some((_, raw)) = value.split_once('=') {
                    let exe = raw.trim().trim_matches('"').to_string();
                    if !exe.is_empty() {
                        return (windows_gui_python(exe), Vec::new());
                    }
                }
            }
        }
    }

    (default_python_command(), Vec::new())
}

#[cfg(windows)]
fn windows_gui_python(exe: String) -> String {
    let path = PathBuf::from(&exe);
    if path
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case("python.exe"))
    {
        let pythonw = path.with_file_name("pythonw.exe");
        if pythonw.exists() {
            return pythonw.to_string_lossy().into_owned();
        }
    }
    exe
}

#[cfg(windows)]
fn default_python_command() -> String {
    std::env::var_os("PATH")
        .and_then(|paths| {
            std::env::split_paths(&paths)
                .map(|path| path.join("pythonw.exe"))
                .find(|path| path.exists())
        })
        .map(|path| path.to_string_lossy().into_owned())
        .unwrap_or_else(|| "python".to_string())
}

#[cfg(not(windows))]
fn default_python_command() -> String {
    "python".to_string()
}

#[cfg(not(windows))]
fn windows_gui_python(exe: String) -> String {
    exe
}

fn spawn_api(app: &AppHandle) -> Option<Child> {
    if desktop_mode() == DesktopMode::Remote {
        return None;
    }
    if api_is_available() {
        return None;
    }

    let root = project_root(app);
    let web_api = root.join("app").join("web_api.py");
    let (python, prefix) = python_command(&root);
    let log_dir = root.join("logs").join("desktop");
    let _ = std::fs::create_dir_all(&log_dir);
    let boot_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    let stdout_log = std::fs::File::create(log_dir.join(format!("api_boot_{boot_id}_stdout.log")))
        .ok()
        .map(Stdio::from)
        .unwrap_or_else(Stdio::null);
    let stderr_log = std::fs::File::create(log_dir.join(format!("api_boot_{boot_id}_stderr.log")))
        .ok()
        .map(Stdio::from)
        .unwrap_or_else(Stdio::null);

    let mut command = Command::new(python);
    command
        .args(prefix)
        .args(["-B", "-X", "utf8"])
        .arg(web_api)
        .arg("--home")
        .arg(&root)
        .arg("--host")
        .arg(local_api_host())
        .arg("--port")
        .arg(local_api_port().to_string())
        .current_dir(&root)
        .env("FUND_AGENT_HOME", &root)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(stdout_log)
        .stderr(stderr_log);

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command.spawn().ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ApiProcess(Mutex::new(None)))
        .setup(|app| {
            let runtime = runtime_config();
            eprintln!(
                "OKRA desktop mode={} api_base={}",
                runtime.mode, runtime.diagnostic_api_base
            );
            if runtime.mode == "remote" && !runtime.configured {
                eprintln!("OKRA remote mode is missing OKRA_REMOTE_API_BASE or VITE_OKRA_API_BASE");
            }
            if let Some(child) = spawn_api(app.handle()) {
                if let Some(state) = app.try_state::<ApiProcess>() {
                    if let Ok(mut slot) = state.0.lock() {
                        *slot = Some(child);
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![desktop_runtime_config])
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let child = {
                    let state = window.state::<ApiProcess>();
                    state.0.lock().ok().and_then(|mut slot| slot.take())
                };
                if let Some(mut child) = child {
                    let _ = child.kill();
                };
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running OKRA Workbench");
}

#[cfg(test)]
mod tests {
    use super::{diagnostic_api_base, parse_desktop_mode, DesktopMode};

    #[test]
    fn desktop_mode_defaults_to_local() {
        assert_eq!(parse_desktop_mode(None), DesktopMode::Local);
        assert_eq!(parse_desktop_mode(Some("unknown")), DesktopMode::Local);
        assert_eq!(parse_desktop_mode(Some("REMOTE")), DesktopMode::Remote);
    }

    #[test]
    fn diagnostic_api_base_removes_credentials_and_query() {
        assert_eq!(
            diagnostic_api_base("https://user:secret@okra.example.com/api?token=secret"),
            "https://okra.example.com/api"
        );
    }
}
