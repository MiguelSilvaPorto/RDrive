"""Combo de letra de montagem — paridade com Qt/Web (letras livres + Automático)."""

from __future__ import annotations

import sys
from typing import Iterable

import customtkinter as ctk

from rdrive.core.mount.drive_letters import (
    is_drive_letter_slot,
    mount_label_to_slot_index,
    normalize_mount_slot,
)
from rdrive.core.mount.drive_validation import (
    list_available_mount_letters,
    suggest_mount_letter,
)
from rdrive.models.drive import Drive
from rdrive.ui.ctk.theme import THEME, font_family

MOUNT_AUTO_LABEL = "Automático"
MOUNT_FIELD_LABEL = "Letra da unidade"

TOOLTIP_MOUNT_COMBO = (
    "Escolha uma letra livre ou «Automático» para a primeira letra disponível no sistema."
)
TOOLTIP_SUGGEST_LETTER = (
    "Atualiza a lista e seleciona a primeira letra livre (exclui letras já usadas por outras unidades)."
)


def ctk_mount_letter_combo_values(
    drives: Iterable[Drive],
    *,
    exclude_id: str | None = None,
    allow_mountpoint: str | None = None,
    drive_letters_only: bool | None = None,
) -> list[str]:
    """Valores do combo: ``Automático`` seguido de letras/pontos disponíveis."""
    if drive_letters_only is None:
        drive_letters_only = sys.platform == "win32"

    available = list_available_mount_letters(
        drives,
        exclude_id=exclude_id,
        allow_mountpoint=allow_mountpoint,
    )
    if drive_letters_only:
        available = [slot for slot in available if is_drive_letter_slot(slot)]

    current = normalize_mount_slot(allow_mountpoint or "")
    if current and current not in available:
        available = sorted(
            {*available, current},
            key=lambda slot: mount_label_to_slot_index(slot) or 9999,
        )

    return [MOUNT_AUTO_LABEL, *available]


def mountpoint_from_display(display: str) -> str:
    """Valor para ``resolve_mountpoint`` — vazio significa automático."""
    text = (display or "").strip()
    if not text or text == MOUNT_AUTO_LABEL:
        return ""
    return text


def display_from_mountpoint(mountpoint: str) -> str:
    slot = normalize_mount_slot(mountpoint)
    if slot:
        return slot
    if not (mountpoint or "").strip():
        return MOUNT_AUTO_LABEL
    return (mountpoint or "").strip()


def refresh_mount_letter_combo(
    combo: ctk.CTkComboBox,
    drives: Iterable[Drive],
    *,
    exclude_id: str | None = None,
    allow_mountpoint: str | None = None,
    select: str | None = None,
) -> str:
    """Repreenche o combo; devolve o mountpoint lógico (``""`` = automático)."""
    values = ctk_mount_letter_combo_values(
        drives,
        exclude_id=exclude_id,
        allow_mountpoint=allow_mountpoint,
    )
    combo.configure(values=values or [MOUNT_AUTO_LABEL])

    desired = display_from_mountpoint(select if select is not None else (allow_mountpoint or ""))
    if desired not in values:
        desired = MOUNT_AUTO_LABEL if MOUNT_AUTO_LABEL in values else values[0]

    combo.set(desired)
    return mountpoint_from_display(desired)


def suggest_mount_letter_in_combo(
    combo: ctk.CTkComboBox,
    drives: Iterable[Drive],
    *,
    exclude_id: str | None = None,
) -> str:
    """Atualiza opções e seleciona a letra sugerida; devolve mountpoint ou ``""``."""
    values = ctk_mount_letter_combo_values(drives, exclude_id=exclude_id)
    combo.configure(values=values or [MOUNT_AUTO_LABEL])

    suggested = suggest_mount_letter(drives, exclude_id=exclude_id)
    if suggested:
        display = display_from_mountpoint(suggested)
        if display in values:
            combo.set(display)
            return suggested
    combo.set(MOUNT_AUTO_LABEL)
    return ""


def create_mount_letter_combo(
    parent: ctk.CTkBaseClass,
    *,
    width: int | None = None,
) -> ctk.CTkComboBox:
    """``CTkComboBox`` só-leitura com estilo RDrive."""
    kwargs: dict = {
        "values": [MOUNT_AUTO_LABEL],
        "height": 34,
        "corner_radius": THEME.radius_input,
        "fg_color": THEME.surface_input,
        "border_color": THEME.border_chrome,
        "button_color": THEME.surface_button,
        "button_hover_color": THEME.surface_button_hover,
        "dropdown_fg_color": THEME.bg_surface_2,
        "text_color": THEME.text_default,
        "font": ctk.CTkFont(family=font_family(), size=12),
        "state": "readonly",
    }
    if width is not None:
        kwargs["width"] = width
    combo = ctk.CTkComboBox(parent, **kwargs)
    bind_mount_letter_tooltip(combo)
    _wrap_combo_command_for_tooltip(combo)
    return combo


_TOOLTIP_SHOW_DELAY_MS = 350

# Um único tooltip ativo — evita órfãos ao passar combo → botão «Sugerir letra».
_active_tooltip: dict[str, object] = {
    "win": None,
    "after_id": None,
    "owner": None,
}


def dismiss_mount_letter_tooltip() -> None:
    """Fecha o tooltip de letra de montagem visível (idempotente)."""
    after_id = _active_tooltip.get("after_id")
    owner = _active_tooltip.get("owner")
    if after_id is not None and owner is not None:
        try:
            owner.after_cancel(after_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    _active_tooltip["after_id"] = None

    win = _active_tooltip.get("win")
    _active_tooltip["win"] = None
    _active_tooltip["owner"] = None
    if win is None:
        return
    try:
        if win.winfo_exists():  # type: ignore[attr-defined]
            win.destroy()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _install_global_tooltip_dismiss(root: ctk.CTk) -> None:
    """Regista Escape/clique global e Unmap (minimizar) uma vez por janela raiz."""
    attr = "_rdrive_mount_tooltip_dismiss_bound"
    if getattr(root, attr, False):
        return
    setattr(root, attr, True)

    def _on_escape(_event: object) -> None:
        if _active_tooltip["win"] is not None:
            dismiss_mount_letter_tooltip()

    def _on_global_click(_event: object) -> None:
        if _active_tooltip["win"] is None:
            return
        root.after_idle(dismiss_mount_letter_tooltip)

    def _on_unmap(event: object) -> None:
        if _active_tooltip["win"] is None:
            return
        if getattr(event, "widget", None) is root:
            dismiss_mount_letter_tooltip()

    root.bind_all("<Escape>", _on_escape, add="+")
    root.bind_all("<Button-1>", _on_global_click, add="+")
    root.bind("<Unmap>", _on_unmap, add="+")


def bind_mount_letter_tooltip(widget: ctk.CTkBaseClass, text: str = TOOLTIP_MOUNT_COMBO) -> None:
    """Tooltip leve (``CTkToplevel`` sem decoração) em pt-BR com dismiss robusto."""

    def _show_now() -> None:
        _active_tooltip["after_id"] = None
        if not widget.winfo_exists():
            return
        dismiss_mount_letter_tooltip()

        tw = ctk.CTkToplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        label = ctk.CTkLabel(
            tw,
            text=text,
            fg_color=THEME.bg_surface_2,
            text_color=THEME.text_default,
            corner_radius=6,
            font=ctk.CTkFont(family=font_family(), size=11),
            wraplength=280,
            justify="left",
        )
        label.pack(padx=8, pady=6)
        tw.update_idletasks()
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tw.geometry(f"+{x}+{y}")
        _active_tooltip["win"] = tw
        _active_tooltip["owner"] = widget

        root = widget.winfo_toplevel()
        _install_global_tooltip_dismiss(root)
        tw.bind("<Leave>", lambda _e: dismiss_mount_letter_tooltip())
        tw.bind("<Destroy>", lambda _e: dismiss_mount_letter_tooltip())

    def _schedule_show(_event: object) -> None:
        if not widget.winfo_exists():
            return
        dismiss_mount_letter_tooltip()
        _active_tooltip["owner"] = widget
        _active_tooltip["after_id"] = widget.after(_TOOLTIP_SHOW_DELAY_MS, _show_now)

    def _cancel_or_hide(_event: object | None = None) -> None:
        owner = _active_tooltip.get("owner")
        if owner is widget or _active_tooltip.get("win") is not None:
            dismiss_mount_letter_tooltip()

    widget.bind("<Enter>", _schedule_show, add="+")
    widget.bind("<Leave>", _cancel_or_hide, add="+")
    widget.bind("<Button-1>", _cancel_or_hide, add="+")
    widget.bind("<FocusOut>", _cancel_or_hide, add="+")
    widget.bind("<Destroy>", lambda _e: _cancel_or_hide(), add="+")


def _wrap_combo_command_for_tooltip(combo: ctk.CTkComboBox) -> None:
    """Esconde tooltip ao escolher valor no dropdown."""
    previous = combo.cget("command")

    def _wrapped(choice: str) -> None:
        dismiss_mount_letter_tooltip()
        if callable(previous):
            previous(choice)

    combo.configure(command=_wrapped)
