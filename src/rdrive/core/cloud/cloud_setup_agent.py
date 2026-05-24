"""Assistente de configuração de nuvem — um fluxo ponta-a-ponta por provedor.

Orquestra validação, sugestões (nome/remote/letra), OAuth automático (quando
suportado) ou abertura do assistente rclone manual, e opcionalmente grava a
unidade no cofre RDrive.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import Event
from typing import Any
from uuid import uuid4

from rdrive.core.cloud.auto_connect import (
    AutoConnectService,
    ConnectStage,
    merge_backend_connect_options,
)
from rdrive.core.mount.drive_validation import suggest_mount_letter
from rdrive.core.logging.human_log import HumanLevel, log_exception_event, log_user_event
from rdrive.core.rclone.rclone import RcloneCli, RcloneError
from rdrive.core.cloud.remote_setup import (
    build_guided_rclone_options,
    canonical_backend,
    check_guided_rclone_backend,
    derive_remote_name,
    display_name_for_backend,
    format_guided_connection_error,
    guided_test_remote_path,
    launch_setup_flow,
    suggest_remote_name,
    supports_guided_setup,
    validate_guided_answers,
)
from rdrive.core.cloud.terabox_setup import (
    TERABOX_MAIN_URL,
    is_terabox_provider,
    terabox_backend_available,
    terabox_backend_missing_message,
    test_terabox_remote,
)
from rdrive.models.drive import Drive

ProgressCallback = Callable[["CloudSetupStage", str], None]


class CloudSetupStage(str, Enum):
    VALIDATING = "validating"
    SUGGESTING = "suggesting"
    CONNECTING = "connecting"
    BROWSER = "browser"
    REMOTE = "remote"
    GUIDED = "guided"
    TESTING = "testing"
    SAVING = "saving"
    MANUAL = "manual"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


_STAGE_LABELS_PT: dict[CloudSetupStage, str] = {
    CloudSetupStage.VALIDATING: "A validar provedor…",
    CloudSetupStage.SUGGESTING: "A sugerir nome e letra…",
    CloudSetupStage.CONNECTING: "A preparar ligação…",
    CloudSetupStage.BROWSER: "A ligar conta — conclua o login no browser",
    CloudSetupStage.REMOTE: "A criar remote no rclone…",
    CloudSetupStage.GUIDED: "A configurar credenciais…",
    CloudSetupStage.TESTING: "A testar ligação…",
    CloudSetupStage.SAVING: "A guardar unidade…",
    CloudSetupStage.MANUAL: "Configuração manual necessária",
    CloudSetupStage.DONE: "Concluído",
    CloudSetupStage.ERROR: "Falhou",
    CloudSetupStage.CANCELLED: "Cancelado",
}


def stage_label_pt(stage: CloudSetupStage) -> str:
    return _STAGE_LABELS_PT.get(stage, stage.value)


_CONNECT_TO_SETUP: dict[ConnectStage, CloudSetupStage] = {
    ConnectStage.CONNECTING: CloudSetupStage.CONNECTING,
    ConnectStage.BROWSER: CloudSetupStage.BROWSER,
    ConnectStage.SAVING: CloudSetupStage.REMOTE,
    ConnectStage.TESTING: CloudSetupStage.TESTING,
    ConnectStage.DONE: CloudSetupStage.DONE,
    ConnectStage.ERROR: CloudSetupStage.ERROR,
    ConnectStage.FALLBACK: CloudSetupStage.MANUAL,
}


@dataclass(slots=True)
class CloudSetupPlan:
    """Valores sugeridos ou confirmados antes de executar o fluxo."""

    provider: str
    label: str
    remote_name: str
    mountpoint: str


@dataclass(slots=True)
class CloudSetupResult:
    success: bool
    stage: CloudSetupStage
    message: str
    plan: CloudSetupPlan
    drive_id: str | None = None
    used_manual: bool = False
    used_guided: bool = False
    cancelled: bool = False


@dataclass(slots=True)
class CloudSetupState:
    """Snapshot serializável para ``getCloudSetupState``."""

    running: bool = False
    stage: str = ""
    message: str = ""
    provider: str = ""
    label: str = ""
    remote_name: str = ""
    mountpoint: str = ""
    success: bool | None = None
    drive_id: str | None = None
    used_manual: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "stage": self.stage,
            "message": self.message,
            "provider": self.provider,
            "label": self.label,
            "remote_name": self.remote_name,
            "mountpoint": self.mountpoint,
            "success": self.success,
            "drive_id": self.drive_id,
            "used_manual": self.used_manual,
            "error": self.error,
        }


class CloudSetupAgent:
    """Agente dedicado: liga conta + prepara unidade RDrive com mínima intervenção."""

    def __init__(
        self,
        rclone_cli: RcloneCli,
        *,
        auto_connect: AutoConnectService | None = None,
    ) -> None:
        self.rclone = rclone_cli
        self.auto_connect = auto_connect or AutoConnectService(rclone_cli)

    @staticmethod
    def supports_full_auto(provider: str) -> bool:
        return AutoConnectService.supports_auto_connect(provider)

    @staticmethod
    def supports_guided(provider: str) -> bool:
        return supports_guided_setup(provider)

    def build_plan(
        self,
        provider: str,
        *,
        label: str = "",
        remote_name: str = "",
        mountpoint: str = "",
        drives: list[Drive] | None = None,
        onedrive_type: str | None = None,
    ) -> CloudSetupPlan:
        backend = canonical_backend(provider)
        display = display_name_for_backend(backend)
        resolved_label = (label or "").strip() or f"{display} Pessoal"
        if not remote_name.strip():
            if onedrive_type and str(onedrive_type).lower() in {
                "business",
                "empresarial",
                "365",
                "work",
                "enterprise",
            }:
                remote = "onedrive_empresarial"
            else:
                remote = derive_remote_name(resolved_label, backend)
                if remote == suggest_remote_name(backend):
                    remote = suggest_remote_name(backend)
        else:
            remote = remote_name.strip()
        letter = (mountpoint or "").strip()
        if not letter and drives is not None:
            letter = suggest_mount_letter(drives)
        return CloudSetupPlan(
            provider=backend,
            label=resolved_label,
            remote_name=remote,
            mountpoint=letter,
        )

    def run(
        self,
        provider: str,
        *,
        label: str = "",
        remote_name: str = "",
        mountpoint: str = "",
        drives: list[Drive] | None = None,
        save_drive: bool = True,
        session_only: bool = False,
        connect_now: bool = True,
        onedrive_type: str | None = None,
        tenant: str | None = None,
        guided_answers: dict[str, Any] | None = None,
        progress: ProgressCallback | None = None,
        cancel_event: Event | None = None,
        save_drive_fn: Callable[[Drive], str] | None = None,
    ) -> CloudSetupResult:
        """Executa o fluxo completo; respeita ``cancel_event`` entre etapas."""

        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage, message)

        def _cancelled(plan: CloudSetupPlan) -> CloudSetupResult:
            msg = "Configuração cancelada."
            _emit(CloudSetupStage.CANCELLED, msg)
            return CloudSetupResult(
                False,
                CloudSetupStage.CANCELLED,
                msg,
                plan,
                cancelled=True,
            )

        def _check_cancel(plan: CloudSetupPlan) -> CloudSetupResult | None:
            if cancel_event and cancel_event.is_set():
                return _cancelled(plan)
            return None

        backend = canonical_backend(provider)
        plan = self.build_plan(
            backend,
            label=label,
            remote_name=remote_name,
            mountpoint=mountpoint,
            drives=drives,
            onedrive_type=onedrive_type,
        )

        _emit(CloudSetupStage.VALIDATING, stage_label_pt(CloudSetupStage.VALIDATING))
        if cancelled := _check_cancel(plan):
            return cancelled

        try:
            backends = self.rclone.list_backends(timeout=15)
            if backends and backend not in backends:
                if is_terabox_provider(backend):
                    if not guided_answers:
                        _emit(
                            CloudSetupStage.GUIDED,
                            terabox_backend_missing_message(),
                        )
                        return CloudSetupResult(
                            False,
                            CloudSetupStage.GUIDED,
                            terabox_backend_missing_message(),
                            plan,
                        )
                else:
                    msg = (
                        f"O backend «{backend}» não está disponível neste rclone. "
                        "Atualize o rclone ou escolha outro provedor."
                    )
                    _emit(CloudSetupStage.ERROR, msg)
                    return CloudSetupResult(False, CloudSetupStage.ERROR, msg, plan)
        except RcloneError:
            pass

        _emit(CloudSetupStage.SUGGESTING, stage_label_pt(CloudSetupStage.SUGGESTING))
        if drives is not None and not plan.mountpoint:
            plan = CloudSetupPlan(
                provider=plan.provider,
                label=plan.label,
                remote_name=plan.remote_name,
                mountpoint=suggest_mount_letter(drives),
            )
        if cancelled := _check_cancel(plan):
            return cancelled

        if AutoConnectService.supports_auto_connect(backend):
            return self._run_oauth_path(
                plan,
                save_drive=save_drive,
                session_only=session_only,
                connect_now=connect_now,
                onedrive_type=onedrive_type,
                tenant=tenant,
                progress=progress,
                cancel_event=cancel_event,
                save_drive_fn=save_drive_fn,
                check_cancel=_check_cancel,
            )

        if supports_guided_setup(backend):
            if guided_answers:
                return self._run_guided_path(
                    plan,
                    guided_answers=guided_answers,
                    save_drive=save_drive,
                    session_only=session_only,
                    connect_now=connect_now,
                    progress=progress,
                    check_cancel=_check_cancel,
                    save_drive_fn=save_drive_fn,
                )
            if is_terabox_provider(backend):
                hint = (
                    "Use «Abrir Chrome do RDrive», exporte cookies.txt e "
                    "«Importar cookie (Chrome)». "
                    f"Após login em /main (ex.: {TERABOX_MAIN_URL}), "
                    "clique «Ligar e guardar»."
                )
                _emit(CloudSetupStage.GUIDED, hint)
                return CloudSetupResult(
                    False,
                    CloudSetupStage.GUIDED,
                    hint,
                    plan,
                )
            _emit(
                CloudSetupStage.GUIDED,
                "Preencha o formulário guiado para continuar.",
            )
            return CloudSetupResult(
                False,
                CloudSetupStage.GUIDED,
                "Aguardando credenciais no formulário guiado.",
                plan,
            )

        return self._run_manual_path(
            plan,
            setup_message=(
                f"{display_name_for_backend(backend)} requer credenciais no terminal. "
                "Abra o assistente rclone, preencha host/chaves conforme solicitado "
                f"e use o remote «{remote}». Depois volte ao RDrive para guardar a unidade."
            ).format(remote=plan.remote_name),
            progress=progress,
            check_cancel=_check_cancel,
        )

    def _run_oauth_path(
        self,
        plan: CloudSetupPlan,
        *,
        save_drive: bool,
        session_only: bool,
        connect_now: bool,
        onedrive_type: str | None,
        tenant: str | None,
        progress: ProgressCallback | None,
        cancel_event: Event | None,
        save_drive_fn: Callable[[Drive], str] | None,
        check_cancel: Callable[[CloudSetupPlan], CloudSetupResult | None],
    ) -> CloudSetupResult:
        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage, message)

        def _oauth_progress(connect_stage: ConnectStage, message: str) -> None:
            mapped = _CONNECT_TO_SETUP.get(connect_stage, CloudSetupStage.CONNECTING)
            _emit(mapped, message or stage_label_pt(mapped))

        connect_options = merge_backend_connect_options(
            plan.provider,
            onedrive_type=onedrive_type,
            tenant=tenant,
        )

        if cancelled := check_cancel(plan):
            return cancelled

        result = self.auto_connect.start_oauth_flow(
            plan.provider,
            plan.remote_name,
            options=connect_options,
            progress=_oauth_progress,
        )

        if cancel_event and cancel_event.is_set():
            return CloudSetupResult(
                False,
                CloudSetupStage.CANCELLED,
                "Configuração cancelada.",
                plan,
                cancelled=True,
            )

        if not result.success:
            stage = _CONNECT_TO_SETUP.get(result.stage, CloudSetupStage.ERROR)
            if result.used_fallback:
                return self._run_manual_path(
                    plan,
                    setup_message=result.message,
                    progress=progress,
                    check_cancel=check_cancel,
                )
            _emit(stage, result.message)
            return CloudSetupResult(False, stage, result.message, plan)

        plan = CloudSetupPlan(
            provider=plan.provider,
            label=plan.label,
            remote_name=result.remote_name or plan.remote_name,
            mountpoint=plan.mountpoint,
        )

        if not save_drive or save_drive_fn is None:
            msg = "Conta ligada. Pode guardar a unidade no assistente."
            _emit(CloudSetupStage.DONE, msg)
            return CloudSetupResult(True, CloudSetupStage.DONE, msg, plan)

        if cancelled := check_cancel(plan):
            return cancelled

        return self._persist_drive(
            plan,
            session_only=session_only,
            connect_now=connect_now,
            save_drive_fn=save_drive_fn,
            progress=progress,
        )

    def run_guided_manual_setup(
        self,
        plan: CloudSetupPlan,
        answers: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Cria remote rclone de forma não-interativa e valida com ``lsd``."""
        self._create_and_test_guided_remote(plan, answers, progress=progress)

    def test_guided_connection(
        self,
        provider: str,
        answers: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> tuple[bool, str]:
        """Testa credenciais com remote temporário (sem guardar unidade)."""
        backend = canonical_backend(provider)
        plan = CloudSetupPlan(
            provider=backend,
            label="",
            remote_name=f"_rdrive_probe_{uuid4().hex[:8]}",
            mountpoint="",
        )
        try:
            self._create_and_test_guided_remote(plan, answers, progress=progress)
            return True, "Ligação testada com sucesso."
        except ValueError as exc:
            return False, str(exc).strip() or "Falha ao testar ligação."
        except Exception as exc:  # noqa: BLE001
            return False, format_guided_connection_error(backend, str(exc))

    def _create_and_test_guided_remote(
        self,
        plan: CloudSetupPlan,
        answers: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        backend = canonical_backend(plan.provider)

        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage, message)

        ok, detail = validate_guided_answers(backend, answers)
        if not ok:
            raise ValueError(detail)

        ok_backend, backend_msg = check_guided_rclone_backend(backend, self.rclone)
        if not ok_backend:
            raise ValueError(backend_msg)

        options = build_guided_rclone_options(backend, answers)
        if not options:
            raise ValueError("Nenhuma opção válida foi gerada a partir do formulário.")

        _emit(CloudSetupStage.GUIDED, stage_label_pt(CloudSetupStage.GUIDED))
        remote = plan.remote_name.strip()
        if not remote:
            raise ValueError("Nome de remote em falta.")

        is_probe = remote.startswith("_rdrive_probe_")

        if self.rclone.remote_exists(remote):
            try:
                self.rclone.config_delete(remote)
            except RcloneError:
                pass

        _emit(CloudSetupStage.REMOTE, stage_label_pt(CloudSetupStage.REMOTE))
        create_timeout = 180 if is_terabox_provider(backend) else 120
        try:
            self.rclone.config_create_interactive_loop(
                remote,
                backend,
                options=options,
                timeout=create_timeout,
            )

            _emit(CloudSetupStage.TESTING, stage_label_pt(CloudSetupStage.TESTING))
            if is_terabox_provider(backend):
                test_ok, detail_msg = test_terabox_remote(
                    self.rclone,
                    remote,
                    retries=3,
                    timeout=150,
                )
                if not test_ok:
                    raise ValueError(format_guided_connection_error(backend, detail_msg))
            else:
                test_path = guided_test_remote_path(backend, remote, answers)
                try:
                    self.rclone.lsd(test_path, timeout=45)
                except RcloneError as exc:
                    detail_msg = format_guided_connection_error(backend, str(exc).strip())
                    raise ValueError(f"Falha ao testar ligação: {detail_msg}") from exc
        finally:
            if is_probe and self.rclone.remote_exists(remote):
                try:
                    self.rclone.config_delete(remote)
                except RcloneError:
                    pass

        log_user_event(
            "Assistente nuvem",
            f"Configuração guiada: {display_name_for_backend(backend)}",
            remote,
        )

    def _run_guided_path(
        self,
        plan: CloudSetupPlan,
        *,
        guided_answers: dict[str, Any],
        save_drive: bool,
        session_only: bool,
        connect_now: bool,
        progress: ProgressCallback | None,
        check_cancel: Callable[[CloudSetupPlan], CloudSetupResult | None],
        save_drive_fn: Callable[[Drive], str] | None,
    ) -> CloudSetupResult:
        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage, message)

        if cancelled := check_cancel(plan):
            return cancelled

        backend = plan.provider
        if is_terabox_provider(backend) and not terabox_backend_available(self.rclone):
            return self._run_manual_path(
                plan,
                setup_message=terabox_backend_missing_message(),
                progress=progress,
                check_cancel=check_cancel,
            )

        try:
            self.run_guided_manual_setup(
                plan,
                guided_answers,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception_event("Assistente nuvem guiado", exc, level=HumanLevel.WARN)
            msg = str(exc).strip() or "Configuração guiada falhou."
            _emit(CloudSetupStage.ERROR, msg)
            fallback = self._run_manual_path(
                plan,
                setup_message=(
                    f"{msg}\n\n"
                    "Abra o assistente rclone no terminal para concluir manualmente."
                ),
                progress=progress,
                check_cancel=check_cancel,
            )
            fallback.message = (
                f"{msg}\n\n"
                f"Remote sugerido: {plan.remote_name}\n"
                "O terminal rclone foi aberto como alternativa."
            )
            return fallback

        if cancelled := check_cancel(plan):
            return cancelled

        if not save_drive or save_drive_fn is None:
            msg = f"Remote «{plan.remote_name}» configurado."
            _emit(CloudSetupStage.DONE, msg)
            return CloudSetupResult(
                True,
                CloudSetupStage.DONE,
                msg,
                plan,
                used_guided=True,
            )

        result = self._persist_drive(
            plan,
            session_only=session_only,
            connect_now=connect_now,
            save_drive_fn=save_drive_fn,
            progress=progress,
        )
        return CloudSetupResult(
            result.success,
            result.stage,
            result.message,
            result.plan,
            drive_id=result.drive_id,
            used_guided=True,
        )

    def _run_manual_path(
        self,
        plan: CloudSetupPlan,
        *,
        setup_message: str,
        progress: ProgressCallback | None,
        check_cancel: Callable[[CloudSetupPlan], CloudSetupResult | None],
    ) -> CloudSetupResult:
        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage, message)

        if cancelled := check_cancel(plan):
            return cancelled

        checklist = (
            f"{setup_message}\n\n"
            "Checklist:\n"
            f"• Remote sugerido: {plan.remote_name}\n"
            f"• Nome da unidade: {plan.label}\n"
            f"• Letra sugerida: {plan.mountpoint or '(automática ao guardar)'}\n"
            "• Após configurar no terminal, use «Guardar» no assistente manual do RDrive."
        )
        _emit(CloudSetupStage.MANUAL, "A abrir assistente rclone no terminal…")
        try:
            launch_setup_flow(self.rclone, plan.provider, plan.remote_name)
        except Exception as exc:  # noqa: BLE001
            log_exception_event("Assistente nuvem", exc, level=HumanLevel.WARN)

        log_user_event(
            "Assistente nuvem",
            f"Manual: {display_name_for_backend(plan.provider)}",
            plan.remote_name,
        )
        _emit(CloudSetupStage.MANUAL, checklist)
        return CloudSetupResult(
            False,
            CloudSetupStage.MANUAL,
            checklist,
            plan,
            used_manual=True,
        )

    def _persist_drive(
        self,
        plan: CloudSetupPlan,
        *,
        session_only: bool,
        connect_now: bool,
        save_drive_fn: Callable[[Drive], str],
        progress: ProgressCallback | None,
    ) -> CloudSetupResult:
        def _emit(stage: CloudSetupStage, message: str) -> None:
            if progress:
                progress(stage, message)

        _emit(CloudSetupStage.SAVING, stage_label_pt(CloudSetupStage.SAVING))
        try:
            drive_id = save_drive_fn(
                Drive(
                    id=str(uuid4()),
                    label=plan.label,
                    provider=plan.provider,
                    remote_name=plan.remote_name,
                    mountpoint=plan.mountpoint,
                    session_only=session_only,
                )
            )
        except ValueError as exc:
            msg = str(exc).strip() or "Não foi possível guardar a unidade."
            _emit(CloudSetupStage.ERROR, msg)
            return CloudSetupResult(False, CloudSetupStage.ERROR, msg, plan)
        except Exception as exc:  # noqa: BLE001
            log_exception_event("Assistente nuvem", exc, level=HumanLevel.ERROR)
            msg = str(exc).strip() or "Falha ao guardar a unidade."
            _emit(CloudSetupStage.ERROR, msg)
            return CloudSetupResult(False, CloudSetupStage.ERROR, msg, plan)

        msg = f"Unidade «{plan.label}» configurada."
        if connect_now:
            msg += " A ligar…"
        _emit(CloudSetupStage.DONE, msg)
        log_user_event(
            "Assistente nuvem",
            f"Unidade criada: {plan.label}",
            f"{plan.remote_name} @ {plan.mountpoint}",
        )
        return CloudSetupResult(
            True,
            CloudSetupStage.DONE,
            msg,
            plan,
            drive_id=drive_id,
        )
