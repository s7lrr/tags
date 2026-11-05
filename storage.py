import json
import os
import tempfile
import threading
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.owners_file = DATA / "owners.json"
        self.servers_file = DATA / "servers.json"
        self.logs_file = DATA / "logs.json"
        self._ensure(self.owners_file, {"owners": []})
        self._ensure(self.servers_file, {"guilds": {}})
        self._ensure(self.logs_file, {"events": []})

    def _ensure(self, path, default):
        if not path.exists():
            self._write(path, default)

    def _read(self, path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=path.stem, suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def list_owners(self):
        with self.lock:
            return list(self._read(self.owners_file, {"owners": []}).get("owners", []))

    def is_owner(self, user_id):
        return int(user_id) in self.list_owners()

    def add_owner(self, user_id):
        with self.lock:
            data = self._read(self.owners_file, {"owners": []})
            if int(user_id) not in data["owners"]:
                data["owners"].append(int(user_id))
                self._write(self.owners_file, data)

    def remove_owner(self, user_id):
        with self.lock:
            data = self._read(self.owners_file, {"owners": []})
            data["owners"] = [x for x in data["owners"] if int(x) != int(user_id)]
            self._write(self.owners_file, data)

    def get_guild(self, guild_id):
        with self.lock:
            data = self._read(self.servers_file, {"guilds": {}})
            return data.get("guilds", {}).get(str(guild_id), {
                "tag": None, "role_id": None, "log_channel_id": None, "members_with_tag": []
            })

    def set_guild(self, guild_id, **changes):
        with self.lock:
            data = self._read(self.servers_file, {"guilds": {}})
            guild = data.setdefault("guilds", {}).setdefault(str(guild_id), {
                "tag": None, "role_id": None, "log_channel_id": None, "members_with_tag": []
            })
            guild.update(changes)
            self._write(self.servers_file, data)

    def has_member_tag(self, guild_id, member_id):
        return str(member_id) in set(map(str, self.get_guild(guild_id).get("members_with_tag", [])))

    def set_member_tag(self, guild_id, member_id, enabled):
        with self.lock:
            data = self._read(self.servers_file, {"guilds": {}})
            guild = data.setdefault("guilds", {}).setdefault(str(guild_id), {
                "tag": None, "role_id": None, "log_channel_id": None, "members_with_tag": []
            })
            members = set(map(str, guild.get("members_with_tag", [])))
            if enabled:
                members.add(str(member_id))
            else:
                members.discard(str(member_id))
            guild["members_with_tag"] = sorted(members)
            self._write(self.servers_file, data)

    def add_log(self, event):
        with self.lock:
            data = self._read(self.logs_file, {"events": []})
            data.setdefault("events", []).insert(0, event)
            data["events"] = data["events"][:5000]
            self._write(self.logs_file, data)

    def recent_logs(self, limit=100):
        with self.lock:
            return self._read(self.logs_file, {"events": []}).get("events", [])[:limit]

    def stats(self):
        logs = self.recent_logs(5000)
        return {
            "events": len(logs),
            "added": sum(1 for x in logs if x.get("event") == "TAG_ADDED"),
            "removed": sum(1 for x in logs if x.get("event") == "TAG_REMOVED"),
        }
