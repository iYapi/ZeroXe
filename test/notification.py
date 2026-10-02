import os
from pathlib import Path
import gazu

# Auto-load .env file from project root if it exists
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        with open(_env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

# 1. Point to your Kitsu instance
kitsu_host = os.getenv("KITSU_HOST", "http://localhost:8080/api")
kitsu_event_host = os.getenv("KITSU_EVENT_HOST", "http://localhost:8080")
gazu.set_host(kitsu_host)
gazu.set_event_host(kitsu_event_host)

# 2. Authenticate (use a dedicated bot user or artist credentials)
kitsu_email = os.getenv("KITSU_EMAIL", "user@example.com")
kitsu_password = os.getenv("KITSU_PASSWORD", "password")
gazu.log_in(kitsu_email, kitsu_password)

# 3. Define the callback for incoming events
def on_notification(data):
    # Triggers when a user receives an in-app notification
    print(f"New notification: {data}")

def on_comment_added(data):
    # Triggers when someone posts a note/comment on a task
    print(f"New comment posted: {data}")

# 4. Initialize and bind listeners
event_client = gazu.events.init()
gazu.events.add_listener(event_client, "notification:new", on_notification)
gazu.events.add_listener(event_client, "comment:new", on_comment_added)
gazu.events.add_listener(event_client, "task:update", lambda d: print("Task updated:", d))

print("Listening for Kitsu events... Press Ctrl+C to exit.")

# 5. Run the client (blocking loop)
gazu.events.run_client(event_client)