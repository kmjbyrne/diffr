#[cfg(not(dev))]
use tauri_plugin_shell::ShellExt;
use tauri::Manager;
use std::sync::Mutex;

struct ServerChild(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ServerChild(Mutex::new(None)))
        .setup(|_app| {
            #[cfg(not(dev))]
            {
                let shell = _app.shell();
                let (mut rx, child) = shell
                    .sidecar("diffr")
                    .expect("failed to find diffr sidecar")
                    .args(["--no-open", "--port", "8787"])
                    .spawn()
                    .expect("failed to spawn diffr server");

                _app.state::<ServerChild>().0.lock().unwrap().replace(child);

                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        match event {
                            tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                                let text = String::from_utf8_lossy(&line);
                                eprintln!("[diffr] {}", text);
                            }
                            tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                                let text = String::from_utf8_lossy(&line);
                                eprintln!("[diffr] {}", text);
                            }
                            _ => {}
                        }
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(child) = window
                    .state::<ServerChild>()
                    .0
                    .lock()
                    .unwrap()
                    .take()
                {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running diffr");
}
