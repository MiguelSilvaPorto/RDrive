"""Conexão automática estilo RaiDrive — OAuth via rclone authorize + config create."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from rdrive.core.human_log import HumanLevel, log_exception_event, log_user_event
from rdrive.core.rclone import RcloneCli, RcloneError
from rdrive.core.remote_setup import backend_setup_info, canonical_backend, display_name_for_backend

ProgressCallback = Callable[["ConnectStage", str], None]

# Backends com fluxo OAuth automatizável via ``rclone authorize``.
_AUTO_OAUTH_BACKENDS = frozenset({"drive", "dropbox", "onedrive", "box", "pcloud", "mega"})

# Opções iniciais por backend (defaults seguros para desktop com browser).
_BACKEND_CREATE_DEFAULTS: dict[str, dict[str, str]] = {
    "drive": {},
    "dropbox": {},
    "onedrive": {"drive_type": "personal"},
    "box": {},
    "pcloud": {},
    "mega": {},
}

_ONEDRIVE_BUSINESS_TYPES = frozenset(
    {
        "business",
        "empresarial",
        "work",
        "365",
        "enterprise",
        "corporate",
        "corp",
        "m365",
        "microsoft365",
    }
)


def build_onedrive_rclone_options(
    *,
    onedrive_type: str | None = None,
    tenant: str | None = None,
) -> dict[str, str]:
    """Opções rclone para OneDrive pessoal vs empresarial (Microsoft 365)."""
    raw = (onedrive_type or "personal").strip().lower().replace("-", "_")
    opts: dict[str, str] = {
        "drive_type": "business" if raw in _ONEDRIVE_BUSINESS_TYPES else "personal",
    }
    tenant_val = (tenant or "").strip()
    if tenant_val:
        opts["tenant"] = tenant_val
    return opts


def merge_backend_connect_options(
    backend: str,
    options: dict[str, str] | None = None,
    *,
    onedrive_type: str | None = None,
    tenant: str | None = None,
) -> dict[str, str] | None:
    """Combina opções UI com defaults por backend (ex.: OneDrive empresarial)."""
    backend_slug = canonical_backend(backend)
    merged: dict[str, str] = dict(_BACKEND_CREATE_DEFAULTS.get(backend_slug, {}))
    if options:
        merged.update(options)
    if backend_slug == "onedrive":
        merged.update(
            build_onedrive_rclone_options(onedrive_type=onedrive_type, tenant=tenant)
        )
    return merged or None


class ConnectStage(str, Enum):
    CONNECTING = "connecting"
    BROWSER = "browser"
    SAVING = "saving"
    TESTING = "testing"
    DONE = "done"
    ERROR = "error"
    FALLBACK = "fallback"


class AutoConnectError(RuntimeError):
    """Falha no fluxo automático de ligação OAuth."""


@dataclass(slots=True)
class AutoConnectResult:
    success: bool
    remote_name: str
    backend: str
    stage: ConnectStage
    message: str
    used_fallback: bool = False


class AutoConnectService:
    """Orquestra OAuth e criação de remotes rclone sem terminal manual."""

    def __init__(self, rclone_cli: RcloneCli) -> None:
        self.rclone = rclone_cli

    @staticmethod
    def supports_auto_connect(backend_or_slug: str) -> bool:
        backend = canonical_backend(backend_or_slug)
        return backend in _AUTO_OAUTH_BACKENDS

    def list_configured_remotes(self, timeout: int = 20) -> list[str]:
        return self.rclone.list_remotes(timeout=timeout)

    def validate_remote(
        self,
        remote_name: str,
        *,
        deep: bool = True,
        timeout: int = 30,
    ) -> tuple[bool, str]:
        """Confirma que o remote existe e responde (about ou lsd)."""
        target = remote_name.strip()
        if not target:
            return False, "Nome de remote em falta."
        if not self.rclone.remote_exists(target, timeout=timeout):
            return False, f"Remote «{target}» não existe no rclone."
        if not deep:
            return True, "Remote encontrado."
        try:
            self.rclone.about(target, timeout=timeout)
            return True, "Conta acessível (about)."
        except RcloneError:
            pass
        try:
            self.rclone.lsd(f"{target}:", timeout=timeout)
            return True, "Conta acessível (lsd)."
        except RcloneError as exc:
            return False, str(exc).strip() or "Remote não respondeu ao teste."

    def create_remote_if_missing(
        self,
        backend: str,
        remote_name: str,
        options: dict[str, str] | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> bool:
        """Cria remote apenas se ainda não existir; não sobrescreve."""
        backend_slug = canonical_backend(backend)
        name = remote_name.strip()
        if not name:
            raise AutoConnectError("Informe um nome para o remote.")
        if self.rclone.remote_exists(name):
            return True
        return self._create_remote_with_token_flow(
            backend_slug,
            name,
            options=options,
            progress=progress,
        )

    def start_oauth_flow(
        self,
        backend: str,
        remote_name: str,
        *,
        options: dict[str, str] | None = None,
        progress: ProgressCallback | None = None,
        force_recreate: bool = False,
    ) -> AutoConnectResult:
        """Fluxo completo: authorize → guardar remote → validar."""
        backend_slug = canonical_backend(backend)
        name = remote_name.strip()
        setup = backend_setup_info(backend_slug)

        def _emit(stage: ConnectStage, message: str) -> None:
            if progress:
                progress(stage, message)

        if not name:
            msg = "Defina o nome do remote antes de conectar."
            _emit(ConnectStage.ERROR, msg)
            return AutoConnectResult(False, name, backend_slug, ConnectStage.ERROR, msg)

        if not setup.is_oauth or backend_slug not in _AUTO_OAUTH_BACKENDS:
            msg = (
                f"{setup.backend} requer credenciais manuais. "
                "Use o assistente rclone no terminal."
            )
            _emit(ConnectStage.FALLBACK, msg)
            return AutoConnectResult(
                False, name, backend_slug, ConnectStage.FALLBACK, msg, used_fallback=True
            )

        try:
            if self.rclone.remote_exists(name) and not force_recreate:
                _emit(ConnectStage.TESTING, "A testar remote existente…")
                ok, detail = self.validate_remote(name, deep=True)
                if ok:
                    _emit(ConnectStage.DONE, detail)
                    log_user_event(
                        "Conexão automática",
                        f"Remote «{name}» já configurado",
                        detail,
                    )
                    return AutoConnectResult(
                        True, name, backend_slug, ConnectStage.DONE, detail
                    )
                _emit(ConnectStage.SAVING, "A renovar credenciais…")
                try:
                    self.rclone.config_reconnect(name, timeout=120)
                except RcloneError:
                    pass

            _emit(ConnectStage.CONNECTING, "A preparar ligação OAuth…")
            self._create_remote_with_token_flow(
                backend_slug,
                name,
                options=options,
                progress=progress,
                overwrite=force_recreate or not self.rclone.remote_exists(name),
            )

            _emit(ConnectStage.TESTING, "A validar acesso à conta…")
            ok, detail = self.validate_remote(name, deep=True)
            if not ok:
                raise AutoConnectError(detail)

            _emit(ConnectStage.DONE, "Conta ligada com sucesso.")
            log_user_event(
                "Conexão automática",
                f"Conta «{display_backend(backend_slug)}» ligada",
                f"remote: {name}",
            )
            return AutoConnectResult(
                True, name, backend_slug, ConnectStage.DONE, detail or "Pronto."
            )
        except AutoConnectError as exc:
            _emit(ConnectStage.ERROR, str(exc))
            log_exception_event("Conexão automática", exc, level=HumanLevel.ERROR)
            return AutoConnectResult(
                False, name, backend_slug, ConnectStage.ERROR, str(exc)
            )
        except RcloneError as exc:
            msg = str(exc).strip() or "Comando rclone falhou."
            _emit(ConnectStage.ERROR, msg)
            log_exception_event("Conexão automática", exc, level=HumanLevel.ERROR)
            return AutoConnectResult(
                False, name, backend_slug, ConnectStage.ERROR, msg
            )

    def reconnect_remote(self, remote_name: str) -> bool:
        """Renova token OAuth de um remote existente."""
        target = remote_name.strip()
        if not target:
            return False
        try:
            self.rclone.config_reconnect(target, timeout=120)
            ok, _ = self.validate_remote(target, deep=True)
            return ok
        except RcloneError:
            return False

    def _create_remote_with_token_flow(
        self,
        backend: str,
        remote_name: str,
        *,
        options: dict[str, str] | None = None,
        progress: ProgressCallback | None = None,
        overwrite: bool = True,
    ) -> bool:
        def _emit(stage: ConnectStage, message: str) -> None:
            if progress:
                progress(stage, message)

        if self.rclone.remote_exists(remote_name) and not overwrite:
            return True

        _emit(
            ConnectStage.BROWSER,
            "Browser aberto — conclua o login e autorize o acesso.",
        )
        token_json = self.rclone.authorize(backend, timeout=300)
        if not token_json:
            raise AutoConnectError(
                "Não foi possível obter o token OAuth. "
                "Verifique se concluiu o login no browser."
            )

        _emit(ConnectStage.SAVING, "A guardar remote no rclone…")
        merged: dict[str, str] = dict(_BACKEND_CREATE_DEFAULTS.get(backend, {}))
        if options:
            merged.update({k: v for k, v in options.items() if k != "token"})
        merged["token"] = token_json

        if self.rclone.remote_exists(remote_name) and overwrite:
            try:
                self.rclone.config_delete(remote_name)
            except RcloneError:
                pass

        self.rclone.config_create_interactive_loop(
            remote_name,
            backend,
            merged,
            timeout=180,
        )
        return True


def display_backend(backend: str) -> str:
    return display_name_for_backend(backend)


def stage_label_pt(stage: ConnectStage) -> str:
    labels = {
        ConnectStage.CONNECTING: "A conectar…",
        ConnectStage.BROWSER: "Browser aberto — faça login",
        ConnectStage.SAVING: "A guardar remote…",
        ConnectStage.TESTING: "A testar ligação…",
        ConnectStage.DONE: "Pronto",
        ConnectStage.ERROR: "Falhou",
        ConnectStage.FALLBACK: "Configuração manual necessária",
    }
    return labels.get(stage, stage.value)
