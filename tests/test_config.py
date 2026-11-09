"""Config tests: user-scope paths and capability index locations."""

from __future__ import annotations

from pathlib import Path

from octk.config import ToolkitPaths, user_capabilities_index, user_toolkit_dir


def test_user_dir_honours_octk_user_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCTK_USER_CONFIG", str(tmp_path / "uc"))
    assert user_toolkit_dir() == tmp_path / "uc"


def test_user_dir_honours_xdg_config_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OCTK_USER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert user_toolkit_dir() == tmp_path / "xdg" / "octk"


def test_user_dir_defaults_to_home_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OCTK_USER_CONFIG", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert user_toolkit_dir() == tmp_path / ".config" / "octk"


def test_capability_paths_live_under_toolkit(tmp_path: Path) -> None:
    paths = ToolkitPaths(tmp_path)
    assert paths.capabilities == tmp_path / ".toolkit" / "capabilities"
    assert paths.capabilities_index == paths.capabilities / "index.json"
    assert paths.capabilities_local == paths.capabilities / "local.json"


def test_user_capabilities_index_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCTK_USER_CONFIG", str(tmp_path / "uc"))
    assert user_capabilities_index() == tmp_path / "uc" / "capabilities" / "index.json"
