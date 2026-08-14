from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from core.dashboard_application import is_keiba_filename
from core.prediction_snapshot import KeibaSnapshotError, build_event_snapshot, keiba_bytes, load_keiba, race_snapshot_from_result
from tests.test_prediction_snapshot import result_for


@pytest.fixture()
def valid_keiba_bytes():
    return keiba_bytes(build_event_snapshot([race_snapshot_from_result(result_for())]))


@pytest.mark.parametrize("name", ["saved.keiba", "SAVED.KEIBA", "  saved.KeIbA  "])
def test_keiba_filename_is_accepted_case_insensitively(name):
    assert is_keiba_filename(name)


@pytest.mark.parametrize("name", ["file.pdf", "file.zip", "file.json", "file.html", "image.png", "keiba"])
def test_non_keiba_filename_is_rejected_before_loader(name):
    assert not is_keiba_filename(name)


def _rewrite_archive(data: bytes, *, schema_version=None, tamper_snapshot=False) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        manifest = json.loads(source.read("manifest.json"))
        snapshot = source.read("snapshot.json")
    if schema_version is not None:
        manifest["schema_version"] = schema_version
        payload = json.loads(snapshot); payload["schema_version"] = schema_version
        snapshot = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        manifest["snapshot_sha256"] = hashlib.sha256(snapshot).hexdigest()
    if tamper_snapshot:
        snapshot += b" "
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        target.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        target.writestr("snapshot.json", snapshot)
    return output.getvalue()


def test_empty_and_corrupt_keiba_are_rejected_by_existing_loader():
    with pytest.raises(KeibaSnapshotError): load_keiba(b"")
    with pytest.raises(KeibaSnapshotError): load_keiba(b"not-a-zip")


def test_tampered_keiba_is_rejected_by_sha256(valid_keiba_bytes):
    with pytest.raises(KeibaSnapshotError, match="整合性"):
        load_keiba(_rewrite_archive(valid_keiba_bytes, tamper_snapshot=True))


def test_unsupported_schema_is_rejected(valid_keiba_bytes):
    with pytest.raises(KeibaSnapshotError): load_keiba(_rewrite_archive(valid_keiba_bytes, schema_version=999))


def test_uploader_source_has_no_ios_accept_filter():
    source = (Path(__file__).resolve().parents[1] / "core" / "dashboard_application.py").read_text(encoding="utf-8")
    block = source[source.index('".keibaファイルを選択"'):source.index("if uploaded is None", source.index('".keibaファイルを選択"'))]
    assert 'type=["keiba"]' not in block
