"""Tests for profile storage and workout records.

Run:  python -m pytest        (or: python tests/test_profiles.py)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pose_trainer.storage.profiles import (  # noqa: E402
    MAX_NAME_LEN, ProfileStore, make_record, mode_label, record_results)


def new_store():
    folder = tempfile.mkdtemp()
    return ProfileStore(os.path.join(folder, "data", "profiles.json"))


def fake_summary(reps, exercise="Squat"):
    return {"exercise": exercise, "reps": reps, "half_reps": 1, "good_form_reps": reps,
            "form_issue_reps": 0, "avg_rep_time": 1.8, "avg_depth": 88.0, "best_depth": 80.0}


def fake_results(reps, exercise="Squat"):
    return {"summary": fake_summary(reps, exercise), "duration": 30.0}


def raises_value_error(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def test_add_and_validate_names():
    store = new_store()
    pid = store.add_profile("  Ali   Rezaei ")
    assert store.get(pid)["name"] == "Ali Rezaei"
    assert raises_value_error(store.add_profile, "")
    assert raises_value_error(store.add_profile, "   ")
    assert raises_value_error(store.add_profile, "ali rezaei")      # duplicate, any case
    long_id = store.add_profile("x" * 50)
    assert len(store.get(long_id)["name"]) == MAX_NAME_LEN


def test_new_profile_becomes_active_and_data_survives_reload():
    store = new_store()
    store.add_profile("Ali")
    sara = store.add_profile("Sara")
    assert store.last_profile_id == sara
    reloaded = ProfileStore(store.path)
    assert [p["name"] for p in reloaded.profiles()] == ["Ali", "Sara"]
    assert reloaded.last_profile_id == sara


def test_corrupt_file_is_backed_up():
    store = new_store()
    store.add_profile("Ali")
    with open(store.path, "w") as f:
        f.write("{ not json")
    broken = ProfileStore(store.path)
    assert broken.profiles() == []
    assert os.path.exists(store.path + ".broken")


def test_delete_profile():
    store = new_store()
    pid = store.add_profile("Ali")
    store.add_record(pid, make_record(fake_summary(5), "30s", 30, "live"))
    store.delete_profile(pid)
    assert store.profiles() == [] and store.last_profile_id is None


def test_records_filter_and_best():
    store = new_store()
    pid = store.add_profile("Ali")
    for reps, mode in ((10, "30s"), (14, "30s"), (20, "60s"), (7, "free")):
        store.add_record(pid, make_record(fake_summary(reps), mode, 30, "live"))
    store.add_record(pid, make_record(fake_summary(9, "Push-up"), "30s", 30, "live"))
    assert len(store.records(pid)) == 5
    assert len(store.records(pid, "Squat", "30s")) == 2
    assert store.best_reps(pid, "Squat", "30s") == 14
    assert store.best_reps(pid, "Push-up", "60s") is None


def test_record_results_notes():
    store = new_store()
    pid = store.add_profile("Ali")

    res = fake_results(10)
    assert record_results(store, pid, res, "30s", "live") is not None
    assert res["note_kind"] == "ok" and "Ali" in res["note"]       # first test: just saved

    res = fake_results(12)
    record_results(store, pid, res, "30s", "live")
    assert res["note_kind"] == "best"                                # beat 10

    res = fake_results(11)
    record_results(store, pid, res, "30s", "live")
    assert res["note_kind"] == "ok"                                  # not a new best

    res = fake_results(50)
    record_results(store, pid, res, "free", "video")
    assert res["note_kind"] == "ok"                                  # free mode has no personal best

    res = fake_results(5)
    assert record_results(store, None, res, "30s", "live") is None
    assert res["note_kind"] == "warn"                                # no profile selected
    assert len(store.records(pid)) == 4


def test_record_contents():
    record = make_record(fake_summary(12), "60s", 60, "video")
    assert record["mode"] == "60s" and record["source"] == "video"
    assert record["reps"] == 12 and record["duration"] == 60
    assert mode_label("30s") == "30 s"


if __name__ == "__main__":  # run without pytest
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError:
                failed += 1
                print("FAIL", name)
    sys.exit(1 if failed else 0)