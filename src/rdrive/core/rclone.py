from __future__ import annotations

import json
import os
import platform
import re
import shlex
import subprocess
from rdrive.core.subprocess_utils import popen_logged, run_logged
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_TOKEN_JSON_RE = re.compile(r"\{[^{}]*\"access_token\"[^{}]*\}", re.DOTALL)


def extract_token_json(text: str) -> str:
    """Extrai JSON de token a partir da saída de ``rclone authorize``."""
    payload = text.strip()
    if not payload:
        return ""
    for line in payload.splitlines():
        candidate = line.strip()
        if candidate.startswith("{") and "access_token" in candidate:
            return candidate
    match = _TOKEN_JSON_RE.search(payload)
    if match:
        return match.group(0)
    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        blob = payload[start : end + 1]
        if "access_token" in blob:
            return blob
    return ""


class RcloneError(RuntimeError):
    pass


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def rclone_version_label(stdout: str) -> str:
    """Primeira linha útil de ``rclone version`` (ex.: ``rclone v1.68.2``)."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("rclone"):
            return stripped
    stripped = stdout.strip()
    return stripped.splitlines()[0] if stripped else "—"


class RcloneCli:
    """Thin wrapper around rclone subprocess calls."""

    def __init__(self, executable: str = "rclone") -> None:
        self.executable = executable
        self._version_label_cache: str | None = None

    def run(
        self,
        args: Sequence[str],
        timeout: int = 60,
        *,
        allow_failure: bool = False,
    ) -> CommandResult:
        cmd = [self.executable, *args]
        try:
            proc = run_logged(
                cmd,
                context="rclone",
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RcloneError(
                "rclone não encontrado no PATH. Instale o rclone e tente novamente."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RcloneError(
                f"rclone demorou demais para responder ({timeout}s): {' '.join(cmd)}"
            ) from exc
        result = CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")
        if proc.returncode != 0 and not allow_failure:
            detail = (result.stderr or result.stdout).strip()
            raise RcloneError(
                f"rclone command failed ({proc.returncode}): {' '.join(cmd)}\n"
                f"{detail}"
            )
        return result

    def version(self, timeout: int = 20) -> str:
        return self.run(["version"], timeout=timeout).stdout.strip()

    def version_label(self, timeout: int = 20, *, refresh: bool = False) -> str:
        """Versão curta do rclone, com cache por instância."""
        if not refresh and self._version_label_cache is not None:
            return self._version_label_cache
        try:
            self._version_label_cache = rclone_version_label(self.version(timeout=timeout))
        except RcloneError:
            self._version_label_cache = "Não encontrado no PATH"
        return self._version_label_cache

    def list_remotes(self, timeout: int = 20) -> list[str]:
        return [line.strip(":") for line in self.run(["listremotes"], timeout=timeout).stdout.splitlines() if line]

    def list_backends(self, timeout: int = 20) -> list[str]:
        result = self.run(["help", "backends"], timeout=timeout)
        backends: list[str] = []
        for line in result.stdout.splitlines():
            match = re.match(r"^\s*([a-z0-9_]+)\s{2,}.+$", line.strip())
            if not match:
                continue
            backend = match.group(1).strip()
            if backend and backend not in backends:
                backends.append(backend)
        return backends

    def has_backend(self, backend_name: str) -> bool:
        target = backend_name.strip().lower()
        if not target:
            return False
        return target in {backend.lower() for backend in self.list_backends()}

    def remote_exists(self, remote_name: str, timeout: int = 20) -> bool:
        target = remote_name.strip()
        if not target:
            return False
        return target in self.list_remotes(timeout=timeout)

    def remote_backend(self, remote_name: str) -> str | None:
        target = remote_name.strip()
        if not target:
            return None
        result = self.run(["config", "show", target], timeout=30)
        for line in result.stdout.splitlines():
            entry = line.strip()
            if not entry.lower().startswith("type"):
                continue
            _sep, _eq, value = entry.partition("=")
            backend = value.strip().lower()
            if backend:
                return backend
        return None

    def launch_config_in_terminal(self, remote_name: str | None = None, backend: str | None = None) -> None:
        args = [self.executable, "config"]
        if remote_name and backend:
            args.extend(["create", remote_name.strip(), backend.strip().lower()])
        command = " ".join(shlex.quote(part) for part in args)
        system_name = platform.system().lower()
        if system_name == "windows":
            cmd = ["cmd", "/c", "start", "Rclone Config", "cmd", "/k", command]
            popen_logged(
                cmd,
                context="rclone",
                allow_visible_console=True,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            return
        if system_name == "linux":
            for terminal in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                if not self._command_exists(terminal):
                    continue
                popen_logged(
                    [terminal, "-e", command],
                    context="rclone",
                    allow_visible_console=True,
                )
                return
            raise RcloneError("Nenhum terminal compatível foi encontrado para abrir o rclone config.")
        if system_name == "darwin":
            escaped = command.replace('"', '\\"')
            popen_logged(
                ["osascript", "-e", f'tell application "Terminal" to do script "{escaped}"'],
                context="rclone",
                allow_visible_console=True,
            )
            return
        raise RcloneError(f"Sistema operacional não suportado para abrir terminal: {platform.system()}")

    def _command_exists(self, command: str) -> bool:
        path = os.environ.get("PATH", "")
        for base in path.split(os.pathsep):
            candidate = Path(base) / command
            if candidate.exists():
                return True
        return False

    def about(self, remote: str, timeout: int = 30) -> dict:
        target = remote.strip().rstrip(":")
        result = self.run(["about", f"{target}:", "--json"], timeout=timeout)
        return json.loads(result.stdout or "{}")

    def lsd(self, remote_path: str, timeout: int = 30) -> list[str]:
        result = self.run(["lsd", remote_path], timeout=timeout)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def authorize(self, backend: str, timeout: int = 300) -> str:
        """Executa ``rclone authorize`` e devolve JSON do token OAuth."""
        backend_slug = backend.strip().lower()
        result = self.run(["authorize", backend_slug], timeout=timeout, allow_failure=True)
        combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
        token = extract_token_json(combined)
        if token:
            return token
        if result.returncode != 0:
            detail = combined.strip() or f"authorize falhou (código {result.returncode})"
            raise RcloneError(detail)
        raise RcloneError(
            "Token OAuth não encontrado na saída do rclone authorize. "
            "Conclua o login no browser e tente novamente."
        )

    def config_delete(self, remote_name: str, timeout: int = 30) -> None:
        self.run(["config", "delete", remote_name.strip()], timeout=timeout)

    def config_reconnect(self, remote_name: str, timeout: int = 120) -> None:
        self.run(["config", "reconnect", remote_name.strip()], timeout=timeout)

    def config_create_interactive_loop(
        self,
        remote_name: str,
        backend: str,
        options: dict[str, str] | None = None,
        *,
        timeout: int = 180,
    ) -> None:
        """Completa ``rclone config create`` em modo não-interativo (loop JSON)."""
        name = remote_name.strip()
        backend_slug = backend.strip().lower()
        args: list[str] = ["config", "create", name, backend_slug, "--non-interactive", "--all"]
        if options:
            for key, value in options.items():
                args.extend([key, value])

        state = ""
        for _ in range(40):
            cmd_args = list(args)
            if state:
                cmd_args.extend(["--continue", "--state", state])
            result = self.run(cmd_args, timeout=timeout, allow_failure=True)
            payload_text = (result.stdout or result.stderr).strip()
            if not payload_text:
                if result.returncode == 0:
                    return
                raise RcloneError(
                    payload_text or f"config create falhou (código {result.returncode})"
                )
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                if result.returncode == 0:
                    return
                raise RcloneError(
                    f"Resposta inválida do rclone config create: {payload_text[:200]}"
                ) from exc

            next_state = str(payload.get("State", "") or "")
            if not next_state:
                if result.returncode != 0:
                    error_text = payload.get("Error") or payload_text
                    raise RcloneError(str(error_text))
                return

            option = payload.get("Option") or {}
            answer = self._default_config_answer(
                option, backend_slug, preferences=options
            )
            if answer is None:
                name_key = option.get("Name", "opção")
                raise RcloneError(
                    f"Configuração requer entrada manual ({name_key}). "
                    "Use o assistente rclone no terminal."
                )
            state = next_state
            args = ["config", "create", name, backend_slug, "--non-interactive", "--continue"]
            args.extend(["--state", state, "--result", answer])

    @staticmethod
    def _default_config_answer(
        option: dict,
        backend: str,
        *,
        preferences: dict[str, str] | None = None,
    ) -> str | None:
        """Escolhe resposta automática para perguntas comuns pós-OAuth."""
        prefs = preferences or {}
        name = str(option.get("Name", ""))
        name_lower = name.lower()
        if name and name in prefs and str(prefs[name]).strip():
            return str(prefs[name])
        if name_lower and name_lower in prefs and str(prefs[name_lower]).strip():
            return str(prefs[name_lower])

        default = option.get("Default")
        if default is not None and str(default).strip():
            return str(default)

        if name_lower in {"config_token", "config_is_local"}:
            return "false"

        if backend == "s3":
            if name_lower == "env_auth":
                return str(prefs.get("env_auth", "false"))

        if backend == "onedrive":
            if name_lower in {"drive_type", "type"}:
                drive_type = str(prefs.get("drive_type", "personal")).strip().lower()
                if drive_type in {"business", "personal", "documentlibrary"}:
                    return drive_type
                return "personal"
            if name_lower == "config_type":
                return "onedrive"
            if name_lower == "tenant":
                tenant = str(prefs.get("tenant", "")).strip()
                return tenant
            if name_lower == "drive_id":
                return ""

        if backend == "drive":
            if name_lower == "scope":
                return "drive"

        if backend == "terabox":
            if name_lower == "cookie":
                cookie = str(prefs.get("cookie", "")).strip()
                return cookie or None

        choices = option.get("Examples") or []
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict) and "Value" in first:
                return str(first["Value"])
            if isinstance(first, str):
                return first

        options_map = option.get("Options")
        if isinstance(options_map, list) and options_map:
            entry = options_map[0]
            if isinstance(entry, dict):
                return str(entry.get("Value", entry.get("Name", "")))

        return None

    def lsjson(self, remote_path: str) -> list[dict]:
        result = self.run(["lsjson", remote_path])
        payload = json.loads(result.stdout or "[]")
        if isinstance(payload, list):
            return payload
        return []

    def hashsum(self, algorithm: str, target: str) -> str:
        result = self.run(["hashsum", algorithm, target])
        line = next((ln.strip() for ln in result.stdout.splitlines() if ln.strip()), "")
        if not line:
            return ""
        return line.split()[0]

    def check(self, source: str | Path, dest: str, one_way: bool = True) -> bool:
        args = ["check", str(source), dest]
        if one_way:
            args.append("--one-way")
        self.run(args)
        return True

    def copyto(self, source: str | Path, dest: str, retries: int = 3) -> None:
        self.run(["copyto", str(source), dest, "--retries", str(retries)], timeout=3600)

    def purge(self, target: str) -> None:
        self.run(["purge", target], timeout=600)
