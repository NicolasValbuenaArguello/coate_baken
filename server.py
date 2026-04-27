import customtkinter as ctk
import subprocess
import threading
import json
import os
import psutil
import requests
import webbrowser
import shlex
import re
import socket
from tkinter import messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

SERVERS_FILE = "servers.json"


class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Panel de Servidores PRO")
        self.geometry("1200x650")

        self.processes = {}
        self.logs = {}
        self.selected_server = None
        self.server_widgets = {}  # 🔥 ESTA ES LA CLAVE

        self.load_servers()
        self.build_ui()
        self.after(2000, self.refresh_ui)

    # =============================
    # DATA
    # =============================
    def load_servers(self):
        if os.path.exists(SERVERS_FILE):
            with open(SERVERS_FILE, "r") as f:
                self.servers = json.load(f)
        else:
            self.servers = []

    def save_servers(self):
        with open(SERVERS_FILE, "w") as f:
            json.dump(self.servers, f, indent=4)

    # =============================
    # UI
    # =============================
    def build_ui(self):

        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # PANEL IZQUIERDO
        left = ctk.CTkFrame(main, width=350)
        left.pack(side="left", fill="y", padx=10)

        ctk.CTkLabel(left, text="Servidores", font=("Arial", 18)).pack(pady=10)

        self.server_frame = ctk.CTkScrollableFrame(left)
        self.server_frame.pack(fill="both", expand=True)

        btns = ctk.CTkFrame(left)
        btns.pack(pady=10)

        ctk.CTkButton(btns, text="▶ Iniciar todos", command=self.start_all).pack(side="left", padx=5)
        ctk.CTkButton(btns, text="⏹ Detener todos", command=self.stop_all).pack(side="left", padx=5)

        # FORMULARIO
        form = ctk.CTkFrame(left)
        form.pack(fill="x", pady=10, padx=10)

        ctk.CTkLabel(form, text="Nuevo Servidor").pack(pady=5)

        self.name = ctk.CTkEntry(form, placeholder_text="Nombre")
        self.name.pack(fill="x", pady=5)

        self.cmd = ctk.CTkEntry(form, placeholder_text="Comando")
        self.cmd.pack(fill="x", pady=5)

        self.port = ctk.CTkEntry(form, placeholder_text="Puerto (opcional)")
        self.port.pack(fill="x", pady=5)

        ctk.CTkButton(form, text="➕ Agregar", command=self.add_server).pack(fill="x", pady=8)

        # PANEL DERECHO
        right = ctk.CTkFrame(main)
        right.pack(side="right", fill="both", expand=True, padx=10)

        ctk.CTkLabel(right, text="Consola", font=("Arial", 18)).pack(pady=5)

        self.console = ctk.CTkTextbox(right, font=("Consolas", 12))
        self.console.pack(fill="both", expand=True)

        self.render_servers()

    # =============================
    # UTIL
    # =============================
    def detectar_puerto(self, comando):
        match = re.search(r'--port\s+(\d+)', comando)
        if match:
            return int(match.group(1))
        return None

    def get_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def check_health(self, server):
        try:
            url = f"http://localhost:{server['puerto']}{server.get('health','/')}"
            r = requests.get(url, timeout=1)
            return r.status_code < 500
        except:
            return False

    # =============================
    # RENDER
    # =============================
    def render_servers(self):

        for server in self.servers:

            name = server["nombre"]

            if name in self.server_widgets:
                continue  # ya existe, no lo recrees

            frame = ctk.CTkFrame(self.server_frame)
            frame.pack(fill="x", pady=5, padx=5)

            label = ctk.CTkLabel(frame, text=name)
            label.pack(side="left", padx=5)

            btns = ctk.CTkFrame(frame, fg_color="transparent")
            btns.pack(side="right")

            ctk.CTkButton(btns, text="▶", width=30,
                        command=lambda s=server: self.start_server(s)).pack(side="left")

            ctk.CTkButton(btns, text="⏹", width=30,
                        command=lambda s=server: self.stop_server(s)).pack(side="left")

            ctk.CTkButton(btns, text="📄", width=30,
                        command=lambda s=server: self.select_server(s)).pack(side="left")

            ctk.CTkButton(btns, text="📊", width=30,
                        command=lambda s=server: self.open_metrics(s)).pack(side="left")

            ctk.CTkButton(btns, text="🌐", width=30,
                        command=lambda p=server["puerto"]: webbrowser.open(f"http://localhost:{p}")
                        ).pack(side="left")

            # 🔥 guardamos referencia
            self.server_widgets[name] = {
                "label": label,
                "frame": frame
            }
    
    
    def update_server_status(self):

        for server in self.servers:

            name = server["nombre"]
            widget = self.server_widgets.get(name)

            if not widget:
                continue

            label = widget["label"]

            running = name in self.processes

            status = "STOP"
            color = "#ff4444"

            if running:
                if self.check_health(server):
                    status = "OK"
                    color = "#00ff88"
                else:
                    status = "NO RESP"
                    color = "#ffcc00"

            label.configure(text=f"{name} | {status}", text_color=color)
            
    # =============================
    # LOGS
    # =============================
    def read_output(self, name, process):

        def stream(pipe, tag):
            for line in pipe:
                line = f"[{tag}] {line}"
                self.logs.setdefault(name, []).append(line)

                if self.selected_server == name:
                    self.console.insert("end", line)
                    self.console.see("end")

        threading.Thread(target=stream, args=(process.stdout, "OUT"), daemon=True).start()
        threading.Thread(target=stream, args=(process.stderr, "ERR"), daemon=True).start()

    def select_server(self, server):
        self.selected_server = server["nombre"]
        self.console.delete("0.0", "end")

        for line in self.logs.get(server["nombre"], []):
            self.console.insert("end", line)

    # =============================
    # CONTROL
    # =============================
    def start_server(self, server):

        name = server["nombre"]

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        process = subprocess.Popen(
            shlex.split(server["comando"]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )

        self.processes[name] = {"process": process, "pid": process.pid}

        self.read_output(name, process)

    def stop_server(self, server):
        name = server["nombre"]
        if name in self.processes:
            self.processes[name]["process"].terminate()
            del self.processes[name]

    def start_all(self):
        for s in self.servers:
            self.start_server(s)

    def stop_all(self):
        for p in self.processes.values():
            p["process"].terminate()
        self.processes.clear()

    def refresh_ui(self):
        self.update_server_status()  # 🔥 ya no render completo
        self.after(2000, self.refresh_ui)
    # =============================
    # METRICS
    # =============================
    def open_metrics(self, server):

        if server["nombre"] not in self.processes:
            return

        win = ctk.CTkToplevel(self)
        win.title(f"Métricas - {server['nombre']}")
        win.geometry("300x200")

        label = ctk.CTkLabel(win, text="")
        label.pack(pady=20)

        def update():
            if server["nombre"] in self.processes:
                pid = self.processes[server["nombre"]]["pid"]
                p = psutil.Process(pid)
                cpu = p.cpu_percent(interval=0.1)
                ram = p.memory_info().rss / (1024 * 1024)
                label.configure(text=f"CPU: {cpu:.1f}%\nRAM: {ram:.1f} MB")
                win.after(1000, update)

        update()

    # =============================
    # ADD SERVER
    # =============================
    def add_server(self):

        nombre = self.name.get().strip()
        comando = self.cmd.get().strip()

        if not nombre or not comando:
            messagebox.showerror("Error", "Campos obligatorios")
            return

        comando = comando.replace("start cmd /k", "").replace("--reload", "").strip()

        puerto = self.detectar_puerto(comando)

        if not puerto:
            puerto = self.get_free_port()

        tipo = "api" if "uvicorn" in comando else "script"
        health = "/docs" if tipo == "api" else "/"

        nuevo = {
            "nombre": nombre,
            "comando": comando,
            "puerto": puerto,
            "health": health,
            "tipo": tipo
        }

        self.servers.append(nuevo)
        self.save_servers()
        self.render_servers()

        self.name.delete(0, "end")
        self.cmd.delete(0, "end")
        self.port.delete(0, "end")

        messagebox.showinfo("OK", f"{nombre} agregado")


if __name__ == "__main__":
    app = App()
    app.mainloop()