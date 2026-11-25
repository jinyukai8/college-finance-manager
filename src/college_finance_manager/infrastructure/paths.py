from __future__ import annotations

import os
from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass
from pathlib import Path


INSTALL_CONFIG = "ledger-paths.ini"
INSTALL_REGISTRY_KEY = r"Software\jinyukai8\LaboratoryLedger"


class DataDirectoryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    database: Path
    attachments: Path
    backups: Path
    logs: Path
    lock_file: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        resolved = root.expanduser().resolve()
        return cls(
            root=resolved,
            database=resolved / "finance.db",
            attachments=resolved / "attachments",
            backups=resolved / "backups",
            logs=resolved / "logs",
            lock_file=resolved / "app.lock",
        )

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.attachments.mkdir(exist_ok=True)
        self.backups.mkdir(exist_ok=True)
        self.logs.mkdir(exist_ok=True)


def _legacy_installed_data_dir() -> str | None:
    if os.name != "nt":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INSTALL_REGISTRY_KEY) as key:
            value, kind = winreg.QueryValueEx(key, "DataDir")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DataDirectoryError("无法读取先前安装保存的账本目录") from exc
    if kind == winreg.REG_EXPAND_SZ:
        value = winreg.ExpandEnvironmentStrings(value)
    if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not value.strip():
        raise DataDirectoryError("先前安装保存的账本目录无效")
    return value


def _installed_data_dir(executable: Path) -> Path | None:
    config_path = executable.parent / INSTALL_CONFIG
    try:
        raw = config_path.read_bytes()
    except FileNotFoundError:
        raw = None
    except OSError as exc:
        raise DataDirectoryError(f"无法读取安装配置：{config_path}") from exc
    if raw is None:
        legacy = _legacy_installed_data_dir()
        if legacy is None:
            return None
        directory = Path(legacy)
        if not directory.is_absolute():
            raise DataDirectoryError(f"先前安装保存的账本目录无效：{legacy}")
        return directory
    parser = ConfigParser(interpolation=None)
    try:
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        parser.read_string(raw.decode(encoding))
        directory = parser.get("Paths", "DataDir").strip()
        if not directory:
            raise ValueError("DataDir is empty")
    except (ConfigError, ValueError) as exc:
        raise DataDirectoryError(f"安装配置中的账本目录无效：{config_path}") from exc
    return executable.parent / Path(directory)


def resolve_startup_paths(data_dir: Path | None = None, *, executable: Path | None = None) -> AppPaths | None:
    """Resolve a startup directory without falling back to an unrelated ledger."""
    if data_dir is not None:
        return AppPaths.from_root(data_dir)
    if executable is None:
        return None
    configured = _installed_data_dir(executable)
    if configured is None:
        return None
    if not configured.is_dir():
        raise DataDirectoryError(f"已配置的账本目录不可用：{configured}")
    return AppPaths.from_root(configured)
