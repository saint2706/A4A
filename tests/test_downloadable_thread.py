import os
import sys
import types
from pathlib import Path

sys.modules.setdefault(
    "aiohttp",
    types.SimpleNamespace(ClientSession=None, ClientTimeout=None, TCPConnector=None),
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inb4404 import _resolve_final_name, finalize_part_file


def test_finalize_part_file_handles_duplicate_names(tmp_path):
    previous_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        part_file = tmp_path / "image.jpg.part"
        part_file.write_bytes(b"first")

        final_first = finalize_part_file("image.jpg")
        assert final_first == "image.jpg"
        assert (tmp_path / final_first).read_bytes() == b"first"

        second_part = tmp_path / "image.jpg.part"
        second_part.write_bytes(b"second")

        final_second = finalize_part_file("image.jpg")
        assert final_second == "image.1.jpg"
        assert (tmp_path / final_second).read_bytes() == b"second"
    finally:
        os.chdir(previous_cwd)


def test_resolve_final_name_increments_counters(tmp_path):
    previous_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        base_name = "duplicate.png"

        # Create existing files to force the counter to increment past them
        (tmp_path / base_name).write_bytes(b"a")
        (tmp_path / "duplicate.1.png").write_bytes(b"b")

        assert _resolve_final_name(base_name) == "duplicate.2.png"
    finally:
        os.chdir(previous_cwd)
