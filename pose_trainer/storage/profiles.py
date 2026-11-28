"""Local profile storage (one JSON file in the `data` folder) and workout records.

No database or cloud service: everything stays on this computer.

File layout:
  {"version": 1, "last_profile": "<id>" | null,
   "profiles": [{"id", "name", "created", "records": [ {...}, ... ]}]}
"""
import json
import os
import uuid
from datetime import datetime

from pose_trainer.paths import PROFILES_PATH

MAX_NAME_LEN = 20

# mode key -> (label, duration in seconds or None for free practice)
MODES = {
    "free": ("Free", None),
    "30s": ("30 s", 30),
    "60s": ("60 s", 60),
}


def mode_label(key):
    return MODES.get(key, (str(key), None))[0]


class ProfileStore:
    def __init__(self, path=PROFILES_PATH):
        self.path = path
        self.data = {"version": 1, "last_profile": None, "profiles": []}
        self.load()

    # ---- file handling -----------------------------------------------------
    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles = [
                {
                    "id": str(p["id"]),
                    "name": str(p["name"]),
                    "created": p.get("created", ""),
                    "records": list(p.get("records", [])),
                }
                for p in data["profiles"]
            ]
            self.data = {"version": 1, "last_profile": data.get("last_profile"), "profiles": profiles}
        except (OSError, ValueError, KeyError, TypeError):
            # Corrupt file: keep a copy so nothing is lost, then start fresh.
            broken = self.path + ".broken"
            try:
                os.replace(self.path, broken)
                print(f"Warning: {self.path} could not be read. A copy was kept as {broken}.")
            except OSError:
                print(f"Warning: {self.path} could not be read. Starting with no profiles.")

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file

    # ---- profiles ----------------------------------------------------------
    def profiles(self):
        return list(self.data["profiles"])

    def get(self, profile_id):
        for p in self.data["profiles"]:
            if p["id"] == profile_id:
                return p
        return None

    def find_by_name(self, name):
        wanted = " ".join(str(name).split()).lower()
        for p in self.data["profiles"]:
            if p["name"].lower() == wanted:
                return p
        return None

    def add_profile(self, name):
        """Create a profile and make it the active one. Returns its id."""
        name = " ".join(str(name).split())[:MAX_NAME_LEN]
        if not name:
            raise ValueError("Please enter a name.")
        if self.find_by_name(name):
            raise ValueError(f"A profile named '{name}' already exists.")
        profile_id = uuid.uuid4().hex[:8]
        self.data["profiles"].append({
            "id": profile_id,
            "name": name,
            "created": datetime.now().isoformat(timespec="seconds"),
            "records": [],
        })
        self.data["last_profile"] = profile_id
        self.save()
        return profile_id

    def delete_profile(self, profile_id):
        self.data["profiles"] = [p for p in self.data["profiles"] if p["id"] != profile_id]
        if self.data["last_profile"] == profile_id:
            self.data["last_profile"] = None
        self.save()

    @property
    def last_profile_id(self):
        pid = self.data.get("last_profile")
        return pid if self.get(pid) else None

    def set_last(self, profile_id):
        self.data["last_profile"] = profile_id
        try:
            self.save()
        except OSError:
            pass

    # ---- records -----------------------------------------------------------
    def add_record(self, profile_id, record):
        profile = self.get(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        profile["records"].append(record)
        self.save()

    def records(self, profile_id, exercise=None, mode=None):
        """Records of a profile, oldest first, optionally filtered."""
        profile = self.get(profile_id)
        if profile is None:
            return []
        found = [
            r for r in profile["records"]
            if (exercise is None or r.get("exercise") == exercise)
            and (mode is None or r.get("mode") == mode)
        ]
        return sorted(found, key=lambda r: r.get("date", ""))

    def best_reps(self, profile_id, exercise, mode):
        reps = [r.get("reps", 0) for r in self.records(profile_id, exercise, mode)]
        return max(reps) if reps else None


def make_record(summary, mode, duration, source):
    """Turn an Exercise.summary() into a compact record for the profile file."""
    def rnd(value, digits=2):
        return None if value is None else round(value, digits)

    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "exercise": summary["exercise"],
        "mode": mode,                     # "free", "30s", "60s"
        "source": source,                 # "live" or "video"
        "duration": rnd(duration, 1),
        "reps": summary["reps"],
        "half_reps": summary["half_reps"],
        "good_form_reps": summary["good_form_reps"],
        "form_issue_reps": summary["form_issue_reps"],
        "avg_rep_time": rnd(summary["avg_rep_time"]),
        "avg_depth": rnd(summary["avg_depth"], 1),
        "best_depth": rnd(summary["best_depth"], 1),
    }


def record_results(store, profile_id, results, mode, source):
    """Save a finished session to the profile and add a note for the results screen."""
    summary = results["summary"]
    if store is None or profile_id is None or store.get(profile_id) is None:
        results["note"], results["note_kind"] = "No profile selected - not saved", "warn"
        return None

    previous_best = None
    if mode != "free":
        previous_best = store.best_reps(profile_id, summary["exercise"], mode)
    record = make_record(summary, mode, results["duration"], source)
    try:
        store.add_record(profile_id, record)
    except OSError as exc:
        results["note"], results["note_kind"] = f"Could not save: {exc.strerror or exc}", "warn"
        return None

    if previous_best is not None and summary["reps"] > previous_best:
        results["note"], results["note_kind"] = "NEW PERSONAL BEST!", "best"
    else:
        results["note"] = f"Saved to {store.get(profile_id)['name']}'s profile"
        results["note_kind"] = "ok"
    return record