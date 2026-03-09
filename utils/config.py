import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
import base64
import hashlib


class Config:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.config_dir = Path.home() / ".tapnow"
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._cipher = self._get_cipher()
        self._config = self._load_config()
    
    def _get_cipher(self):
        key_file = self.config_dir / ".key"
        if key_file.exists():
            with open(key_file, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_file, "wb") as f:
                f.write(key)
        return Fernet(key)
    
    def _encrypt(self, text: str) -> str:
        return self._cipher.encrypt(text.encode()).decode()
    
    def _decrypt(self, encrypted_text: str) -> str:
        try:
            return self._cipher.decrypt(encrypted_text.encode()).decode()
        except:
            return ""
    
    def _load_config(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "api_keys": {
                "kling": {"api_key": "", "secret_key": ""},
                "jimeng": {"access_key": "", "secret_key": ""},
                "gemini": {"api_key": "", "base_url": ""},
                "gemini3": {"api_key": ""},
                "gpt52": {"api_key": ""}
            },
            "default_disk": "D",
            "projects": [],
            "current_project": None
        }
    
    def _save_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
    
    def get_api_keys(self, platform: str) -> dict:
        keys = self._config.get("api_keys", {}).get(platform, {})
        result = {}
        for key, value in keys.items():
            if value:
                result[key] = self._decrypt(value)
            else:
                result[key] = ""
        return result
    
    def set_api_keys(self, platform: str, keys: dict):
        if "api_keys" not in self._config:
            self._config["api_keys"] = {}
        encrypted_keys = {}
        for key, value in keys.items():
            encrypted_keys[key] = self._encrypt(value) if value else ""
        self._config["api_keys"][platform] = encrypted_keys
        self._save_config()
    
    def get_default_disk(self) -> str:
        return self._config.get("default_disk", "D")
    
    def set_default_disk(self, disk: str):
        self._config["default_disk"] = disk
        self._save_config()
    
    def get_projects(self) -> list:
        return self._config.get("projects", [])
    
    def add_project(self, project_path: str):
        if "projects" not in self._config:
            self._config["projects"] = []
        if project_path not in self._config["projects"]:
            self._config["projects"].append(project_path)
            self._save_config()
    
    def remove_project(self, project_path: str):
        if project_path in self._config.get("projects", []):
            self._config["projects"].remove(project_path)
            self._save_config()
    
    def get_current_project(self) -> str:
        return self._config.get("current_project")
    
    def set_current_project(self, project_path: str):
        self._config["current_project"] = project_path
        self._save_config()
    
    def get_aivideo_base_path(self) -> Path:
        disk = self.get_default_disk()
        return Path(f"{disk}:/AIVIDEO")
    
    def get_show_help(self) -> bool:
        return self._config.get("show_help", True)
    
    def set_show_help(self, show: bool):
        self._config["show_help"] = show
        self._save_config()
