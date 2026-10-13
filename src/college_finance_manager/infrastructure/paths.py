from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_DIRECTORY_NAME = "CollegeFinanceManager"


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


def default_app_paths() -> AppPaths:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("未找到 LOCALAPPDATA，拒绝猜测正式数据目录")
    return AppPaths.from_root(Path(local_app_data) / APP_DIRECTORY_NAME)
