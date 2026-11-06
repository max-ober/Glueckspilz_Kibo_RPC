import os
import shutil
import time
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

CONFIG_FILE = "sync_config.txt"


def load_config():
  if not os.path.exists(CONFIG_FILE):
    print(
        f"[!] Error: Configuration file '{CONFIG_FILE}' not found. Please"
        " create it."
    )
    exit(1)

  source_dir, dest_dir = None, None
  with open(CONFIG_FILE, "r") as f:
    for line in f:
      line = line.strip()
      if not line or line.startswith("#"):
        continue
      if "=" in line:
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip("\"'")
        if key == "SOURCE_DIR":
          source_dir = val
        elif key == "DEST_DIR":
          dest_dir = val

  return source_dir, dest_dir


class SyncHandler(FileSystemEventHandler):

  def __init__(self, source_dir, dest_dir):
    self.source_dir = source_dir
    self.dest_dir = dest_dir
    # Track recent syncs to prevent rapid duplicate loops
    self.recent_events = {}

  def should_ignore(self, path):
    ignored_patterns = [
        ".git",
        "__pycache__",
        ".pyc",
        ".swp",
        ".swo",
        "~",
        ".tmp",
        ".DS_Store",
    ]
    return any(pattern in path for pattern in ignored_patterns)

  def on_any_event(self, event):
    if event.is_directory or self.should_ignore(event.src_path):
      return

    # Debounce filter: Ignore duplicate events on the same file within 1 second
    current_time = time.time()
    last_time = self.recent_events.get(event.src_path, 0)
    if current_time - last_time < 1.0:
      return
    self.recent_events[event.src_path] = current_time

    rel_path = os.path.relpath(event.src_path, self.source_dir)
    dest_path = os.path.join(self.dest_dir, rel_path)

    try:
      if event.event_type == "deleted":
        if os.path.exists(dest_path):
          os.remove(dest_path)
          print(f"[-] Deleted: {rel_path}")
      else:
        if os.path.exists(event.src_path):
          os.makedirs(os.path.dirname(dest_path), exist_ok=True)
          shutil.copy2(event.src_path, dest_path)
          print(f"[+] Synced: {rel_path}")
    except Exception as e:
      print(f"[!] Error syncing {rel_path}: {e}")


if __name__ == "__main__":
  SOURCE_DIR, DEST_DIR = load_config()

  if not SOURCE_DIR or not os.path.exists(SOURCE_DIR):
    print(
        f"[!] Error: SOURCE_DIR is invalid or does not exist: {SOURCE_DIR}"
    )
    exit(1)
  if not DEST_DIR:
    print("[!] Error: DEST_DIR is not specified in the config file.")
    exit(1)

  # Sanity Check: Prevent overlapping paths
  if os.path.commonpath([SOURCE_DIR, DEST_DIR]) == os.path.abspath(SOURCE_DIR):
    print("[!] CRITICAL ERROR: DEST_DIR cannot be inside SOURCE_DIR!")
    print("    This causes an infinite loop. Fix your sync_config.txt paths.")
    exit(1)

  print("=== KRPC Live Sync Started ===")
  print(f"Watching: {SOURCE_DIR}")
  print(f"Target:   {DEST_DIR}")

  # Perform an initial full sync on startup
  if os.path.exists(DEST_DIR):
    shutil.rmtree(DEST_DIR)
  shutil.copytree(
      SOURCE_DIR,
      DEST_DIR,
      ignore=shutil.ignore_patterns(".git*", "__pycache__", "*.pyc"),
  )
  print("Initial full sync completed successfully.\n")

  event_handler = SyncHandler(SOURCE_DIR, DEST_DIR)
  observer = Observer()
  observer.schedule(event_handler, path=SOURCE_DIR, recursive=True)
  observer.start()

  try:
    while True:
      time.sleep(1)
  except KeyboardInterrupt:
    observer.stop()
    print("\nSync stopped by user.")
  observer.join()