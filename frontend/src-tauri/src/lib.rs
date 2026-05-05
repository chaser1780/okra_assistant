use std::net::TcpStream;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct ApiProcess(Mutex<Option<Child>>);

fn api_is_available() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:8765".parse().expect("valid local API address"),
        Duration::from_millis(250),
    )
    .is_ok()
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
        .unwrap_or_else(|_| PathBuf::from(r"F:\okra_assistant"))
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
    if api_is_available() {
        return None;
    }

    let root = project_root(app);
    let web_api = root.join("app").join("web_api.py");
    let (python, prefix) = python_command(&root);
    let log_dir = root.join("logs").join("desktop");
    let _ = std::fs::create_dir_all(&log_dir);

    let mut command = Command::new(python);
    command
        .args(prefix)
        .args(["-B", "-X", "utf8"])
        .arg(web_api)
        .arg("--home")
        .arg(&root)
        .current_dir(&root)
        .env("FUND_AGENT_HOME", &root)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command.spawn().ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ApiProcess(Mutex::new(None)))
        .setup(|app| {
            if let Some(child) = spawn_api(app.handle()) {
                if let Some(state) = app.try_state::<ApiProcess>() {
                    if let Ok(mut slot) = state.0.lock() {
                        *slot = Some(child);
                    }
                }
            }
            Ok(())
        })
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
