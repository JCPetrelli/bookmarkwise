import json
import os

import pytest

from bookmarkwise import model, profiles
from tests.helpers import DEMO, demo_dict, write


def test_ids_paths_and_roots():
    tree = model.load(DEMO)
    assert tree["1"].is_root and tree["1"].title == "Bookmarks bar"
    work = next(n for n in tree.folders() if n.title == "Work")
    assert work.location == "Bookmarks bar"
    assert tree["1"].snapshot() == {}
    mark = tree.bookmarks()[0]
    assert mark.snapshot() == {"title": mark.title, "url": mark.url}


def test_account_file_is_merged(tmp_path):
    local = demo_dict()
    account = {"roots": {
        "bookmark_bar": {"id": "500", "type": "folder", "name": "Bookmarks bar", "children": [
            {"id": "501", "type": "url", "name": "Account mark", "url": "https://example.org/acct"}]},
        "other": {"id": "502", "type": "folder", "name": "Other", "children": []},
        "synced": {"id": "503", "type": "folder", "name": "Mobile", "children": []},
    }, "sync_metadata": "x"}
    write(tmp_path, local)
    write(tmp_path, account, "AccountBookmarks")
    tree = model.load(tmp_path / "Bookmarks")
    assert "501" in tree and tree["501"].location == "Bookmarks bar (account)"
    assert tree.sync_on and len(tree.files) == 2
    assert len(model.load(tmp_path / "Bookmarks", with_account=False).files) == 1
    # Only an account file, as in a profile that saves everything to the account.
    (tmp_path / "Bookmarks").unlink()
    assert len(model.load(tmp_path).bookmarks()) == 1


def test_clashing_ids_are_refused(tmp_path):
    write(tmp_path, demo_dict())
    write(tmp_path, demo_dict(), "AccountBookmarks")
    with pytest.raises(ValueError):
        model.load(tmp_path / "Bookmarks")


def test_stale_plain_file_warns(tmp_path):
    p = write(tmp_path, demo_dict())
    enc = tmp_path / "EncryptedBookmarks2"
    enc.write_text("x")
    os.utime(p, (1_000_000, 1_000_000))
    assert model.load(p).warnings


def test_profiles_found_with_names(tmp_path):
    data_dir = tmp_path / "Library" / "Application Support" / "Google" / "Chrome"
    (data_dir / "Profile 3").mkdir(parents=True)
    write(data_dir / "Profile 3", demo_dict())
    (data_dir / "Local State").write_text(json.dumps({"profile": {"info_cache": {"Profile 3": {"name": "Work"}}}}))
    found = profiles.find(["chrome"], home=tmp_path, system="Darwin")
    assert found[0]["profile_name"] == "Work" and found[0]["bookmarks"] == 25
