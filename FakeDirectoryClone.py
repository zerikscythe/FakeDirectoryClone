import os
import hashlib
import zlib
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from queue import Queue, Empty
import threading
import sys
import shutil

cancel_flag = threading.Event()
EXCEPTION_FILES = {"_info.txt", "gamelist.xml"}
LOG_FILE = ".fakeclone_completed.log"

def compute_hashes(file_path, chunk_size=65536):
    crc = 0
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
            md5.update(chunk)
            sha1.update(chunk)
    return format(crc & 0xFFFFFFFF, '08x').upper(), md5.hexdigest().upper(), sha1.hexdigest().upper()

def sanitize_rel_path(rel_path):
    return Path(*[part.strip() for part in rel_path.parts])

def load_completed_log(dst_path):
    log_path = dst_path / LOG_FILE
    if not log_path.exists():
        return set()
    with open(log_path, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def append_to_log(dst_path, rel_path):
    with open(dst_path / LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(str(rel_path).replace("\\", "/") + '\n')

def log_error(dst_path, rel_path_str, exc):
    with open(dst_path / "errors.log", 'a', encoding='utf-8', errors='replace') as log:
        log.write(f"{rel_path_str} - {exc.__class__.__name__}: {str(exc)}\n")

def should_skip_file(file_path, src_path):
    try:
        parts = file_path.relative_to(src_path).parts
        if len(parts) >= 3 and parts[0].lower() == "roms":
            if parts[2].lower() in {"images", "videos", "manuals"}:
                return True
    except Exception:
        pass
    return False

def process_file(real_file_path, src_path, dst_path, completed_set):
    if cancel_flag.is_set():
        return False

    rel_path = sanitize_rel_path(real_file_path.relative_to(src_path))
    rel_path_str = str(rel_path).replace("\\", "/")
    if rel_path_str in completed_set:
        return False

    fake_file_path = dst_path / rel_path
    fake_file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if real_file_path.name in EXCEPTION_FILES:
            shutil.copy2(real_file_path, fake_file_path)
        else:
            hashes = compute_hashes(real_file_path)
            with open(fake_file_path, 'w') as f:
                f.write(','.join(hashes))
        append_to_log(dst_path, rel_path)
        return True
    except (FileNotFoundError, PermissionError) as e:
        log_error(dst_path, rel_path_str, e)
        return False

def create_fake_clone_gui(src_dir, dst_dir, max_workers, update_global, gui_queue):
    src_path = Path(src_dir)
    dst_path = Path(dst_dir)
    completed_set = load_completed_log(dst_path)

    all_files = []
    for root, _, files in os.walk(src_path):
        for file in files:
            full_path = Path(root) / file
            rel_path = sanitize_rel_path(full_path.relative_to(src_path))
            if str(rel_path).replace("\\", "/") not in completed_set and not should_skip_file(full_path, src_path):
                all_files.append(full_path)

    file_queue = Queue()
    for f in all_files:
        file_queue.put(f)

    total = len(all_files)
    progress = [0]

    def worker(worker_id):
        while not cancel_flag.is_set():
            try:
                real_file_path = file_queue.get_nowait()
            except Empty:
                return
            filename = real_file_path.name
            folder = real_file_path.parent.name
            gui_queue.put((worker_id, f"{filename} (in /{folder})"))
            if process_file(real_file_path, src_path, dst_path, completed_set):
                progress[0] += 1
                update_global(progress[0], total)

    threads = []
    for i in range(max_workers):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

def gui_select_folders():
    def run_clone():
        src = filedialog.askdirectory(title="Select Source Folder")
        if not src:
            messagebox.showerror("Error", "No source folder selected.")
            return

        dst = filedialog.askdirectory(title="Select Destination Folder")
        if not dst:
            messagebox.showerror("Error", "No destination folder selected.")
            return

        max_workers = os.cpu_count() or 4

        for widget in worker_frame.winfo_children():
            widget.destroy()
        worker_labels.clear()

        for i in range(max_workers):
            label = tk.Label(worker_frame, text=f"Worker {i+1}: idle", anchor='w', width=60)
            label.grid(row=i, column=0, sticky='w')
            worker_labels.append(label)

        global_bar["value"] = 0
        global_label.config(text="Starting...")

        def update_global(completed, total):
            percent = int((completed / total) * 100)
            global_bar["value"] = percent
            global_label.config(text=f"{completed}/{total} files processed")
            root.update_idletasks()

        def poll_gui_queue():
            try:
                while True:
                    worker_id, text = gui_queue.get_nowait()
                    worker_labels[worker_id].config(text=f"Worker {worker_id+1}: {text}")
            except Empty:
                pass
            if not cancel_flag.is_set():
                root.after(100, poll_gui_queue)

        def task():
            create_fake_clone_gui(src, dst, max_workers=max_workers,
                                  update_global=update_global,
                                  gui_queue=gui_queue)
            if not cancel_flag.is_set():
                messagebox.showinfo("Done", "Fake clone creation complete.")
            else:
                messagebox.showinfo("Cancelled", "Operation was cancelled.")

        cancel_flag.clear()
        threading.Thread(target=task, daemon=True).start()
        poll_gui_queue()

    def cancel_clone():
        cancel_flag.set()

    root = tk.Tk()
    root.title("Fake Clone Generator")
    root.geometry("700x600")

    worker_labels = []
    gui_queue = Queue()

    tk.Button(root, text="Select Folders and Start", command=run_clone).pack(pady=10)

    global_bar = ttk.Progressbar(root, length=550)
    global_bar.pack(pady=5)
    global_label = tk.Label(root, text="Waiting...")
    global_label.pack()

    worker_frame = tk.Frame(root)
    worker_frame.pack(pady=10)

    tk.Button(root, text="Cancel", command=cancel_clone).pack(pady=10)
    root.mainloop()

if __name__ == '__main__':
    if len(sys.argv) == 1 or '--gui' in sys.argv:
        gui_select_folders()
    else:
        import argparse

        parser = argparse.ArgumentParser(description='Create fake clone with file hashes.')
        parser.add_argument('src', nargs='?', help='Source directory with real files')
        parser.add_argument('dst', nargs='?', help='Destination directory for fake clone')
        parser.add_argument('--workers', type=int, default=os.cpu_count() or 4, help='Number of worker threads')
        args = parser.parse_args()

        dummy_queue = Queue()
        create_fake_clone_gui(
            args.src,
            args.dst,
            max_workers=args.workers,
            update_global=lambda c, t: None,
            gui_queue=dummy_queue
        )
