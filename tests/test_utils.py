from pathlib import Path

import pytest

from pydependence._core.utils import (
    apply_root_to_path_str,
    assert_valid_import_name,
    assert_valid_module_path,
    assert_valid_tag,
)


def test_assert_valid_tag():
    # does not normalize tag
    assert assert_valid_tag("valid_tag") == "valid_tag"
    assert assert_valid_tag("valid-tag") == "valid-tag"
    with pytest.raises(ValueError):
        assert_valid_tag("")


def test_assert_valid_module_path():
    assert assert_valid_module_path(Path(__file__)) == Path(__file__).resolve()
    with pytest.raises(ValueError):
        assert_valid_module_path("relative/path")
    with pytest.raises(FileNotFoundError):
        assert_valid_module_path("/path/does/not/exist")
    with pytest.raises(RuntimeError):
        assert_valid_module_path(Path.home())  # assuming home directory is not a file


def test_assert_valid_import_name():
    assert assert_valid_import_name("valid.import.name") == "valid.import.name"
    with pytest.raises(NameError):
        assert_valid_import_name("")
    with pytest.raises(NameError):
        assert_valid_import_name("invalid.import.name.")


def test_apply_root_to_path_str():
    root = str(Path.home())
    assert apply_root_to_path_str(root, "relative/path") == str(
        (Path(root) / "relative/path").resolve()
    )
    with pytest.raises(ValueError):
        apply_root_to_path_str("relative/path", "another/relative/path")
    assert apply_root_to_path_str(root, str(Path.home())) == str(Path.home().resolve())
