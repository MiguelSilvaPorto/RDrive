from __future__ import annotations

DEFAULT_LAUNCHER_DISMISS_SEC = 600.0
DEFAULT_LAUNCHER_DEBOUNCE_MS = 1200


class LauncherRestartPromptCoordinator:
    """Coalesce launcher file-change restart prompts (debounce, batch, dismiss)."""

    def __init__(
        self,
        *,
        dismiss_sec: float = DEFAULT_LAUNCHER_DISMISS_SEC,
        debounce_ms: int = DEFAULT_LAUNCHER_DEBOUNCE_MS,
    ) -> None:
        self.dismiss_sec = dismiss_sec
        self.debounce_ms = debounce_ms
        self.prompt_open = False
        self._pending: set[str] = set()
        self._dismissed_until: dict[str, float] = {}

    def queue(self, rel_path: str, now: float) -> bool:
        """Add path to pending batch; False if path is dismissed."""
        if self._is_dismissed(rel_path, now):
            return False
        self._pending.add(rel_path)
        return True

    def take_batch(self, now: float) -> list[str]:
        eligible = sorted(path for path in self._pending if not self._is_dismissed(path, now))
        for path in eligible:
            self._pending.discard(path)
        return eligible

    def dismiss(self, paths: list[str], now: float) -> None:
        until = now + self.dismiss_sec
        for path in paths:
            self._dismissed_until[path] = until

    def clear_pending(self) -> None:
        self._pending.clear()

    def _is_dismissed(self, rel_path: str, now: float) -> bool:
        until = self._dismissed_until.get(rel_path)
        if until is None:
            return False
        if now >= until:
            del self._dismissed_until[rel_path]
            return False
        return True

    @staticmethod
    def format_message(paths: list[str]) -> str:
        if len(paths) == 1:
            return f"Alteração em {paths[0]}.\n\nReiniciar o RDrive agora?"
        shown = paths[:6]
        names = ", ".join(shown)
        extra = len(paths) - len(shown)
        if extra > 0:
            names = f"{names}, … (+{extra})"
        return (
            f"Alterações em {len(paths)} ficheiros ({names}).\n\n"
            "Reiniciar o RDrive agora?"
        )
