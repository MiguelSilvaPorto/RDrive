"""Painel CTk — bateria completa de benchmark de nuvem (Definições → Testes)."""

from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rdrive.core.diagnostics.cloud_benchmark import TEST_LABELS, BenchmarkTestResult
from rdrive.ui.ctk.services import CtkAppContext
from rdrive.ui.ctk.theme import SECTION_BORDER_WIDTH, THEME, content_wraplength, font_family


class CloudBenchmarkPanel(ctk.CTkFrame):
    """UI de benchmark: drive, progresso, log e tabela de resultados."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        context: CtkAppContext,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._context = context
        self._running = False
        self._wrap_labels: list[ctk.CTkLabel] = []
        self._result_rows: list[tuple[ctk.CTkLabel, ...]] = []

        self.grid_columnconfigure(0, weight=1)

        header = self._section(
            self,
            "Benchmark de nuvem",
            "Gera ~100 MB localmente, envia/descarrega na pasta isolada "
            f"«RDriveBench/_rdrive_test_*» e compara integridade (SHA256).",
        )

        row = ctk.CTkFrame(header, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            row,
            text="Unidade:",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
        ).grid(row=0, column=0, padx=(0, 6))
        self._drive_var = ctk.StringVar(value="")
        self._drive_menu = ctk.CTkOptionMenu(
            row,
            variable=self._drive_var,
            values=["—"],
            fg_color=THEME.surface_button,
            button_color=THEME.surface_button_hover,
            button_hover_color=THEME.accent_primary_soft,
            dropdown_fg_color=THEME.bg_surface_2,
            text_color=THEME.text_default,
            corner_radius=THEME.radius_input,
            font=ctk.CTkFont(family=font_family(), size=12),
            command=self._on_drive_changed,
        )
        self._drive_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="Actualizar lista",
            command=self.refresh_drive_list,
            height=30,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.surface_button,
            hover_color=THEME.surface_button_hover,
            text_color=THEME.text_default,
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
        ).grid(row=0, column=2)

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 8))
        self._run_full_btn = ctk.CTkButton(
            actions,
            text="Executar bateria completa",
            command=self._run_full,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.accent_primary,
            hover_color=THEME.accent_primary_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
        )
        self._run_full_btn.pack(side="left", padx=(0, 8))
        self._cancel_btn = ctk.CTkButton(
            actions,
            text="Cancelar",
            command=self._cancel,
            height=34,
            corner_radius=THEME.radius_pill,
            fg_color=THEME.danger,
            hover_color=THEME.danger_hover,
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
            state="disabled",
        )
        self._cancel_btn.pack(side="left")

        ind = ctk.CTkFrame(header, fg_color="transparent")
        ind.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))
        ind.grid_columnconfigure(0, weight=1)
        self._mode_label = ctk.CTkLabel(
            ind,
            text="",
            text_color=THEME.text_muted,
            font=ctk.CTkFont(family=font_family(), size=11),
            anchor="w",
        )
        self._mode_label.grid(row=0, column=0, sticky="w")

        self._progress = ctk.CTkProgressBar(
            header,
            height=14,
            corner_radius=THEME.radius_pill,
            progress_color=THEME.accent_primary,
            fg_color=THEME.bg_surface_2,
            mode="determinate",
        )
        self._progress.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        tests_row = ctk.CTkFrame(header, fg_color="transparent")
        tests_row.grid(row=6, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._individual_buttons: list[ctk.CTkButton] = []
        for test_id, label in TEST_LABELS.items():
            if test_id == "generate_file":
                continue
            btn = ctk.CTkButton(
                tests_row,
                text=label[:28],
                command=lambda tid=test_id: self._run_single(tid),
                height=28,
                corner_radius=THEME.radius_pill,
                fg_color=THEME.surface_button,
                hover_color=THEME.surface_button_hover,
                text_color=THEME.text_default,
                font=ctk.CTkFont(family=font_family(), size=10),
            )
            btn.pack(side="left", padx=(0, 4), pady=2)
            self._individual_buttons.append(btn)

        log_sec = self._section(
            self,
            "Registo",
            "Mensagens detalhadas durante a execução.",
        )
        self._log_view = ctk.CTkTextbox(
            log_sec,
            height=140,
            corner_radius=THEME.radius_input,
            fg_color=THEME.surface_input,
            text_color=THEME.text_default,
            border_color=THEME.border_chrome,
            border_width=1,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._log_view.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._log_view.insert("1.0", "Seleccione uma unidade e execute a bateria.")
        self._log_view.configure(state="disabled")

        table_sec = self._section(
            self,
            "Resumo",
            "Teste | Estado | MB/s | Duração | Notas",
        )
        self._results_frame = ctk.CTkFrame(table_sec, fg_color="transparent")
        self._results_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        self._results_frame.grid_columnconfigure(4, weight=1)
        self._build_results_header(self._results_frame)

        self.bind("<Configure>", self._on_configure, add="+")
        self.refresh_drive_list()

    def on_visible(self) -> None:
        self.refresh_drive_list()

    def _section(self, parent: ctk.CTkBaseClass, title: str, subtitle: str = "") -> ctk.CTkFrame:
        section = ctk.CTkFrame(
            parent,
            fg_color=THEME.bg_surface_2,
            corner_radius=THEME.radius_card,
            border_width=SECTION_BORDER_WIDTH,
            border_color=THEME.border_soft,
        )
        section.grid(sticky="ew", pady=(0, 12), padx=4)
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section,
            text=title,
            text_color=THEME.text_strong,
            anchor="w",
            font=ctk.CTkFont(family=font_family(), size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 2))
        if subtitle:
            sub = ctk.CTkLabel(
                section,
                text=subtitle,
                text_color=THEME.text_muted,
                anchor="w",
                wraplength=720,
                justify="left",
                font=ctk.CTkFont(family=font_family(), size=11),
            )
            sub.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
            self._wrap_labels.append(sub)
        return section

    def _on_configure(self, event: object) -> None:
        if event.widget is not self:  # type: ignore[union-attr]
            return
        width = self.winfo_width()
        if width < 100:
            return
        wrap = content_wraplength(width, padding=72)
        for label in self._wrap_labels:
            label.configure(wraplength=wrap)

    def refresh_drive_list(self) -> None:
        entries = self._context.benchmark_drive_entries()
        labels = [label for label, _did in entries] or ["—"]
        self._drive_menu.configure(values=labels)
        if labels and labels[0] != "—":
            self._drive_var.set(labels[0])
        self._update_mode_hint()

    def _on_drive_changed(self, _choice: str) -> None:
        self._update_mode_hint()

    def _selected_drive_id(self) -> str | None:
        label = self._drive_var.get().strip()
        if not label or label == "—":
            return None
        for entry_label, drive_id in self._context.benchmark_drive_entries():
            if entry_label == label:
                return drive_id
        return None

    def _update_mode_hint(self) -> None:
        drive_id = self._selected_drive_id()
        if not drive_id:
            self._mode_label.configure(text="Nenhuma unidade disponível.")
            return
        hint = self._context.benchmark_drive_mode_hint(drive_id)
        self._mode_label.configure(text=hint)

    def _append_log(self, line: str) -> None:
        self._log_view.configure(state="normal")
        self._log_view.insert("end", line + "\n")
        self._log_view.see("end")
        self._log_view.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        state = "normal" if not busy else "disabled"
        self._run_full_btn.configure(state=state)
        self._cancel_btn.configure(state="normal" if busy else "disabled")
        for btn in self._individual_buttons:
            btn.configure(state=state)
        if busy:
            self._progress.configure(mode="determinate")
            self._progress.set(0)
        else:
            self._progress.set(0)

    def _run_full(self) -> None:
        self._start_benchmark("full")

    def _run_single(self, test_id: str) -> None:
        self._start_benchmark(test_id)

    def _start_benchmark(self, suite: str) -> None:
        if self._running:
            return
        drive_id = self._selected_drive_id()
        if not drive_id:
            messagebox.showinfo(
                "Benchmark",
                "Seleccione uma unidade configurada (montada ou com remote).",
                parent=self.winfo_toplevel(),
            )
            return
        if not messagebox.askyesno(
            "Benchmark de nuvem",
            (
                "Cria ficheiros temporários na nuvem e localmente (~100 MB+ tráfego).\n\n"
                "Usa apenas a pasta RDriveBench/_rdrive_test_* no remote.\n\n"
                "Continuar?"
            ),
            parent=self.winfo_toplevel(),
        ):
            return

        self._clear_results_table()
        self._log_view.configure(state="normal")
        self._log_view.delete("1.0", "end")
        self._log_view.configure(state="disabled")
        self._append_log(f"A iniciar bateria ({suite})…")
        self._set_busy(True)

        def on_progress(test_id: str, fraction: float, message: str) -> None:
            pct = int(fraction * 100)
            self.after(0, lambda: self._on_progress_ui(test_id, pct, message))

        def on_result(result: BenchmarkTestResult) -> None:
            self.after(0, lambda: self._on_result_ui(result))

        def on_finished(results: list[BenchmarkTestResult]) -> None:
            self.after(0, lambda: self._on_finished_ui(results))

        self._context.run_cloud_benchmark(
            drive_id,
            suite=suite,
            on_progress=on_progress,
            on_result=on_result,
            on_finished=on_finished,
        )

    def _on_progress_ui(self, test_id: str, pct: int, message: str) -> None:
        self._progress.set(pct / 100.0)
        label = TEST_LABELS.get(test_id, test_id)
        self._append_log(f"[{pct:3d}%] {label}: {message}")

    def _on_result_ui(self, result: BenchmarkTestResult) -> None:
        self._add_result_row(result)

    def _on_finished_ui(self, results: list[BenchmarkTestResult]) -> None:
        self._set_busy(False)
        passed = sum(1 for r in results if r.status == "pass")
        failed = sum(1 for r in results if r.status == "fail")
        self._append_log(f"Concluído: {passed} OK, {failed} falhas, {len(results)} total.")

    def _cancel(self) -> None:
        self._context.cancel_cloud_benchmark()
        self._append_log("Cancelamento solicitado…")

    def _build_results_header(self, parent: ctk.CTkFrame) -> None:
        headers = ("Teste", "Estado", "MB/s", "Duração", "Notas")
        for col, text in enumerate(headers):
            ctk.CTkLabel(
                parent,
                text=text,
                text_color=THEME.text_muted,
                font=ctk.CTkFont(family=font_family(), size=10, weight="bold"),
                anchor="w",
            ).grid(row=0, column=col, sticky="w", padx=(0, 8), pady=(0, 4))

    def _clear_results_table(self) -> None:
        for row in self._result_rows:
            for widget in row:
                widget.destroy()
        self._result_rows.clear()

    def _add_result_row(self, result: BenchmarkTestResult) -> None:
        parent = self._results_frame
        row_idx = len(self._result_rows) + 1
        name, status, speed, dur, notes = result.summary_row()
        color = {
            "OK": THEME.success,
            "Falha": THEME.state_error,
            "Cancelado": THEME.warning,
            "Ignorado": THEME.text_muted,
        }.get(status, THEME.text_default)
        widgets: list[ctk.CTkLabel] = []
        for col, (text, anchor) in enumerate(
            (
                (name, "w"),
                (status, "w"),
                (speed, "e"),
                (dur, "e"),
                (notes, "w"),
            )
        ):
            lbl = ctk.CTkLabel(
                parent,
                text=text,
                text_color=color if col == 1 else THEME.text_default,
                font=ctk.CTkFont(family=font_family(), size=10),
                anchor=anchor,
                wraplength=280 if col == 4 else 0,
                justify="left",
            )
            lbl.grid(row=row_idx, column=col, sticky="ew", padx=(0, 8), pady=1)
            widgets.append(lbl)
        self._result_rows.append(tuple(widgets))
