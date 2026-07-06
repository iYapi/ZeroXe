import os
import platform
import json
import sys
from cryptography.fernet import Fernet
from dotenv import load_dotenv

def get_config_dir(app_name="myapp") -> str:
    system = platform.system()

    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming")), app_name)
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~/Library/Application Support"), app_name)
    else:  # Linux and others
        return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), app_name)


class Settings:
    APP_NAME = "ZerØXe"
    BUILD_VERSION = "v0.0.16"

    VERSIONING_FOLDER="progress"
    VERSIONING_LOG_FOLDER=".zeroxe"
    VERSIONING_STARTWITH="v"

    CONFIG_DIR = get_config_dir(APP_NAME)
    SESSION_FILE = os.path.join(CONFIG_DIR, "user", "user_data.dat")
    FILES_DIR = os.path.join(CONFIG_DIR, "files")
    AVATAR_FILE = os.path.join(FILES_DIR, "user", "avatar.png")

    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(FILES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(AVATAR_FILE), exist_ok=True)

    print_log = False

    def __init__(self):
        env_paths = [
            os.path.join(os.path.dirname(__file__), '.env'),  # Same directory as this file
            os.path.join(os.getcwd(), '.env'),  # Current working directory
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),  # Absolute path of this file
        ]
        
        env_loaded = False
        for env_path in env_paths:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                env_loaded = True
                print(f"Loaded .env from: {env_path}")
                break
        
        if not env_loaded:
            # Try loading without specific path (searches default locations)
            load_dotenv()
            print("Loaded .env from default locations")
            
        # Get configuration from environment variables
        self.KITSU_API_URL = os.environ.get("KITSU_API_URL")
        self.KITSU_ALT_API_URL = os.environ.get("KITSU_ALT_API_URL")
        
        # Validate required configuration
        if not self.KITSU_API_URL:
            raise ValueError("KITSU_API_URL environment variable not set. Please configure it in your .env file.")
        
        if not self.KITSU_ALT_API_URL:
            raise ValueError("KITSU_ALT_API_URL environment variable not set. Please configure it in your .env file.")
        # Get FERNET_KEY from environment
        fernet_key = os.environ.get("FERNET_KEY")
        
        if not fernet_key:
            # Check if running as PyInstaller bundle
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_path = sys._MEIPASS
                env_path = os.path.join(base_path, '.env')
                if os.path.exists(env_path):
                    load_dotenv(env_path)
                    fernet_key = os.environ.get("FERNET_KEY")
            
            if not fernet_key:
                raise ValueError("FERNET_KEY environment variable not set. Please configure it in your .env file.")
        # Fernet expects the key as bytes (already base64-encoded from .env)
        key_bytes = fernet_key.encode() if isinstance(fernet_key, str) else fernet_key
        self.cipher = Fernet(key_bytes)

    def save_user_data(self, data):
        os.makedirs(os.path.dirname(self.SESSION_FILE), exist_ok=True)

        json_data = json.dumps(data).encode()
        encrypted_json = self.cipher.encrypt(json_data)

        with open(self.SESSION_FILE, "wb") as f:
            f.write(encrypted_json)

    def read_user_data(self):
        if os.path.exists(self.SESSION_FILE):
            with open(self.SESSION_FILE, "rb") as f:
                encrypted = f.read()
                if encrypted:
                    try:
                        decrypted = self.cipher.decrypt(encrypted)
                        return json.loads(decrypted.decode())
                    except Exception as e:
                        print("Decrypt error:", e)
        return None

    def update_user_field(self, key, value):
        data = self.read_user_data() or {}
        data[key] = value
        self.save_user_data(data)