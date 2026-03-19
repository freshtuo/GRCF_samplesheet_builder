# views.py
# UI appearance
# 

from __future__ import annotations

import inspect
from nicegui import ui
from typing import List, Dict, Any, Optional
from pathlib import Path

from tkinter import Tk, filedialog

from samplesheet_tool.ui.state import (
    RunState, LaneStatus, PlanIntegrityError, Message, 
    save_plan, load_plan, default_store_dir, 
    make_sample_uid, split_sample_uid, 
)
from samplesheet_tool.ui import actions
from samplesheet_tool.ui.shared_catalog import load_shared_catalog, shared_project_path
from samplesheet_tool.ui.runtime_config import RuntimeConfig, save_runtime_config, FLOWCELL_PRESETS
from samplesheet_tool.ui import __version__

# -------------------------
# small helpers
# -------------------------

def status_dot(status: LaneStatus) -> str:
    return {
        LaneStatus.OK: "🟢",
        LaneStatus.WARNING: "🟠",
        LaneStatus.ERROR: "🔴",
    }[status]

def panel_btn(btn: Any) -> Any:
    """
    Unified button style for white panels (Indexes/Projects/Samples/Lanes/Messages).
    No strong colors, no red borders, no heavy contrast.
    ** input and output object should be ui.button ** 
    """
    # base: light fill + thin border + subtle shadow
    btn.props("no-caps flat color=none")
    btn.classes(
        "font-medium "
        "bg-gray-100 hover:bg-gray-200 "
        "text-gray-800 "
        "px-3 py-1.5 rounded-md "
        "border border-gray-300 hover:border-gray-400 "
        "shadow-sm hover:shadow-md "
        "hover:ring-1 hover:ring-gray-300 "
        "focus:outline-none focus:ring-2 focus:ring-gray-400 "
        "transition-all duration-150"
    )

    return btn


def _sync_catalog_if_projects_missing(state: RunState) -> None:
    """Refresh the shared catalog if local project entries reference deleted project files."""
    if state.shared_catalog_dir is None or not state.catalog.projects:
        return

    try:
        missing = [
            pid for pid in state.catalog.projects.keys()
            if not shared_project_path(state.shared_catalog_dir, pid).exists()
        ]
    except PermissionError as e:
        state.startup_warning = (
            f"No permission to read the shared catalog folder: {e}. "
            'The app is still usable with the last loaded in-memory data. Use "Refresh Shared" after access is restored.'
        )
        ui.notify(state.startup_warning, type="negative")
        return
    except Exception as e:
        ui.notify(f"Shared catalog sync check failed: {e}", type="warning")
        return

    if not missing:
        return

    try:
        actions.refresh_shared_catalog(state)
    except Exception as e:
        ui.notify(f"Shared catalog refresh failed: {e}", type="warning")
        return
    preview = ", ".join(sorted(missing)[:3])
    suffix = "..." if len(missing) > 3 else ""
    ui.notify(
        f"Shared catalog changed; removed project(s) no longer available locally: {preview}{suffix}",
        type="warning",
    )


def _project_signature(state: RunState) -> tuple[tuple[str, str], ...]:
    """Return a lightweight signature of shared projects for change detection."""
    return tuple(
        sorted(
            (pid, state.catalog.project_updated_at.get(pid, ""))
            for pid in state.catalog.projects.keys()
        )
    )


def _format_project_refresh_notice(
    old_sig: tuple[tuple[str, str], ...],
    new_sig: tuple[tuple[str, str], ...],
) -> str:
    """Summarize shared-project changes for a single user-facing notice."""
    old_map = dict(old_sig)
    new_map = dict(new_sig)
    added = sorted(set(new_map) - set(old_map))
    removed = sorted(set(old_map) - set(new_map))
    changed = sorted(
        pid for pid in (set(old_map) & set(new_map))
        if old_map[pid] != new_map[pid]
    )
    parts: list[str] = []
    if added:
        parts.append(f"added: {len(added)}")
    if removed:
        parts.append(f"removed: {len(removed)}")
    if changed:
        parts.append(f"updated: {len(changed)}")
    summary = ", ".join(parts) if parts else "content changed"
    return f"Shared projects updated ({summary})."


def _flush_pending_project_refresh(state: RunState, refresh_all) -> None:
    """Apply any deferred project refresh once the UI is no longer in a modal state."""
    if state.ui_modal_open:
        return
    if state.pending_ui_redraw:
        state.pending_ui_redraw = False
        refresh_all()
        return
    if not state.pending_project_refresh:
        return
    notice = state.pending_project_refresh_notice or "Shared projects updated."
    state.pending_project_refresh = False
    state.pending_project_refresh_notice = None
    state.ensure_valid_project_selection()
    ui.notify(notice, type="warning")
    refresh_all()


def _register_dialog_lifecycle(dialog, state: RunState, refresh_all) -> None:
    """Track dialog visibility so background refresh can avoid disruptive redraws."""
    dialog.on("show", lambda _e: setattr(state, "ui_modal_open", True))
    dialog.on("hide", lambda _e: _on_dialog_hide(state))


def tracked_dialog(state: RunState, refresh_all):
    """Create a dialog with lifecycle hooks for deferred background refresh."""
    dialog = ui.dialog()
    _register_dialog_lifecycle(dialog, state, refresh_all)
    return dialog


def _on_dialog_hide(state: RunState) -> None:
    """Mark dialogs closed so deferred refresh can be flushed by the background timer."""
    if state.native_picker_open:
        return
    state.ui_modal_open = False


def _run_safe_ui_background_task(state: RunState, refresh_all, fn, label: str) -> None:
    """Run a background UI callback defensively so unexpected errors do not break the session."""
    try:
        fn()
    except Exception as e:
        warning = f"{label} failed: {e}"
        if state.startup_warning != warning:
            state.startup_warning = warning
            if not state.ui_modal_open:
                refresh_all()
            else:
                state.pending_ui_redraw = True
        print(warning)


def _background_refresh_shared_catalog(state: RunState, refresh_all) -> None:
    """Poll the shared catalog and apply quiet or deferred updates as needed."""
    if state.shared_catalog_dir is None:
        return

    try:
        new_catalog = load_shared_catalog(state.shared_catalog_dir)
    except PermissionError as e:
        warning = (
            f"No permission to read the shared catalog folder: {e}. "
            'The app is still usable with the last loaded in-memory data. Use "Refresh Shared" after access is restored.'
        )
        if state.startup_warning != warning:
            state.startup_warning = warning
            ui.notify(warning, type="negative")
            if not state.ui_modal_open:
                refresh_all()
            else:
                state.pending_ui_redraw = True
        return
    except Exception as e:
        warning = (
            f"Shared catalog auto-refresh failed: {e}. "
            'The app is still usable with the last loaded in-memory data. Use "Refresh Shared" to try again.'
        )
        if state.startup_warning != warning:
            state.startup_warning = warning
            ui.notify(warning, type="warning")
            if not state.ui_modal_open:
                refresh_all()
            else:
                state.pending_ui_redraw = True
        return

    old_project_sig = _project_signature(state)
    new_project_sig = tuple(
        sorted((pid, new_catalog.project_updated_at.get(pid, "")) for pid in new_catalog.projects.keys())
    )
    project_changed = old_project_sig != new_project_sig

    old_index_marker = state.catalog.indexes_updated_at or ""
    new_index_marker = new_catalog.indexes_updated_at or ""
    index_changed = old_index_marker != new_index_marker
    
    # warning_cleared means 
    # there used to be a warning banner, and now it has been cleared
    warning_cleared = bool(state.startup_warning)
    state.startup_warning = None

    if not index_changed and not project_changed:
        if warning_cleared and not state.ui_modal_open:
            refresh_all()
        elif warning_cleared:
            state.pending_ui_redraw = True
        return

    state.catalog.last_loaded_at = new_catalog.last_loaded_at

    if project_changed:
        state.catalog = new_catalog
        notice = _format_project_refresh_notice(old_project_sig, new_project_sig)
        if state.ui_modal_open:
            state.pending_project_refresh = True
            state.pending_project_refresh_notice = notice
            return
        state.ensure_valid_project_selection()
        ui.notify(notice, type="warning")
        refresh_all()
        return

    if index_changed:
        state.catalog.index_tables = new_catalog.index_tables
        state.catalog.indexes_updated_at = new_catalog.indexes_updated_at
        state.catalog.indexes_updated_by = new_catalog.indexes_updated_by
        state.catalog.last_loaded_at = new_catalog.last_loaded_at
        if warning_cleared and not state.ui_modal_open:
            refresh_all()
        elif warning_cleared:
            state.pending_ui_redraw = True

# -------------------------
# lane reads helpers
# -------------------------

def lane_used_reads_m(state: RunState, lane_id: int) -> int:
    total = 0
    for _uid, per_lane in state.assignments.items():
        total += int(per_lane.get(lane_id, 0))
    return total

# -------------------------
# decorator: if anything changes, invalidate the validation state
# -------------------------

def invalidate_validation(state: RunState):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            state.validation_result = None
            state.has_run_level_error = False
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# -------------------------
# toolbar
# -------------------------

SAMPLE_SUMMARY_COLUMNS = [
    {"name": "project", "label": "Project", "field": "project", "sortable": True},
    {"name": "sample", "label": "Sample", "field": "sample", "sortable": True},
    {"name": "required", "label": "Required (M)", "field": "required", "sortable": True},
    {"name": "allocated", "label": "Allocated (M)", "field": "allocated", "sortable": True},
    {"name": "remaining", "label": "Remaining (M)", "field": "remaining", "sortable": True},
    {"name": "status", "label": "Status", "field": "status", "sortable": True},
    {"name": "lanes", "label": "Lanes", "field": "lanes"},
]

ASSIGNMENT_DETAIL_COLUMNS = [
    {"name": "project", "label": "Project", "field": "project", "sortable": True},
    {"name": "sample", "label": "Sample", "field": "sample", "sortable": True},
    {"name": "lane", "label": "Lane", "field": "lane", "align": "right"},
    {
        "name": "allocated_reads",
        "label": "Allocated reads (M)",
        "field": "allocated_reads",
        "align": "right",
        "sortable": True, 
    },
]

PROJECT_SUMMARY_COLUMNS = [
    {"name": "project", "label": "Project", "field": "project", "sortable": True},
    {"name": "library_type", "label": "Library type", "field": "library_type", "sortable": True}, 
    {"name": "sequencing_type", "label": "Sequencing type", "field": "sequencing_type", "sortable": True}, 
    {
        "name": "n_samples",
        "label": "# Samples",
        "field": "n_samples",
        "align": "right",
        "sortable": True, 
    },
    {
        "name": "total_allocated_reads",
        "label": "Total allocated (M)",
        "field": "total_allocated_reads",
        "align": "right",
        "sortable": True, 
    },
    {"name": "lanes", "label": "Lanes", "field": "lanes"},
]


def open_settings_dialog(state: RunState, refresh_all):
    """create a pop-up dialog for changing settings"""
    cfg = RuntimeConfig(
        flowcell_type=state.flowcell_type, 
        n_lanes=state.n_lanes,
        lane_capacity_m=state.lane_capacity_m,
        output_dir=str(state.output_dir),
        shared_catalog_dir=str(state.shared_catalog_dir) if state.shared_catalog_dir else None,
        user_name=state.user_name,
        read1_len=state.read1_len,
        read2_len=state.read2_len,
        max_plans=state.max_plans,
    )

    chosen_paths = {
        "output_dir": str(state.output_dir),
        "shared_catalog_dir": str(state.shared_catalog_dir) if state.shared_catalog_dir else "",
    }

    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-full"):
        ui.label("Runtime Settings").classes("text-lg font-bold")

        ui.separator()

        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            flowcell_select = ui.select(
                options=list(FLOWCELL_PRESETS.keys()),
                value=cfg.flowcell_type,
                label="Flowcell Type",
            ).classes("flex-1")
            lanes_input = ui.number("Number of Lanes", value=cfg.n_lanes).classes("flex-1")
            capacity_input = ui.number("Reads per Lane (M)", value=cfg.lane_capacity_m).classes("flex-1")

        # update n_lanes, lane_capacity_m based on selected flowcell
        def on_flowcell_change(e):
            preset = FLOWCELL_PRESETS.get(flowcell_select.value)
            if not preset:
                return

            lanes_input.value = preset["n_lanes"]
            capacity_input.value = preset["lane_capacity_m"]

        flowcell_select.on_value_change(on_flowcell_change)

        ui.separator()

        ##ui.label("Storage")

        # base dir: display only
        base_input = ui.input("Base Folder", value=str(state.base_dir)).classes("w-full").props("readonly")

        def _set_input_value(widget, value: str) -> None:
            """Keep NiceGUI input widgets and dialog-local state in sync."""
            if hasattr(widget, "set_value"):
                widget.set_value(value)
            else:
                widget.value = value
                widget.update()

        def _close_settings_dialog() -> None:
            """Close the settings dialog and release the modal-open guard explicitly."""
            state.ui_modal_open = False
            state.native_picker_open = False
            dialog.close()

        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            output_input = ui.input("Output Folder", value=str(state.output_dir)).classes("grow")
            output_input.on_value_change(
                lambda e: chosen_paths.__setitem__("output_dir", (e.value or "").strip())
            )

            def choose_output_folder():
                state.ui_modal_open = True
                state.native_picker_open = True
                root = Tk()
                root.withdraw()
                try:
                    root.attributes("-topmost", True)
                    root.lift()
                    root.focus_force()
                except Exception:
                    pass
                folder = filedialog.askdirectory()
                root.destroy()
                state.native_picker_open = False
                # Native folder pickers can transiently hide the web dialog; keep modal protection active.
                state.ui_modal_open = True
                if folder:
                    chosen_paths["output_dir"] = folder
                    _set_input_value(output_input, folder)

            panel_btn(ui.button("Choose Output Folder", on_click=choose_output_folder)).classes("shrink-0")

        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            shared_input = ui.input(
                "Shared Catalog Folder",
                value=cfg.shared_catalog_dir or "",
                placeholder=r"Example: Z:\grcf_samplesheet_catalog or \\server\labshare\grcf_samplesheet_catalog",
            ).classes("grow")
            shared_input.on_value_change(
                lambda e: chosen_paths.__setitem__("shared_catalog_dir", (e.value or "").strip())
            )

            def choose_shared_folder():
                state.ui_modal_open = True
                state.native_picker_open = True
                root = Tk()
                root.withdraw()
                try:
                    root.attributes("-topmost", True)
                    root.lift()
                    root.focus_force()
                except Exception:
                    pass
                folder = filedialog.askdirectory()
                root.destroy()
                state.native_picker_open = False
                # Native folder pickers can transiently hide the web dialog; keep modal protection active.
                state.ui_modal_open = True
                if folder:
                    chosen_paths["shared_catalog_dir"] = folder
                    _set_input_value(shared_input, folder)

            panel_btn(ui.button("Choose Shared Folder", on_click=choose_shared_folder)).classes("shrink-0")

        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            user_input = ui.input(
                "User Name",
                value=cfg.user_name or "",
                placeholder="Example: taz2008",
            ).classes("flex-1")

            max_plans_input = ui.number("Max saved plans", value=cfg.max_plans).classes("flex-1")

        ui.separator()

        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            r1_input = ui.number("Read1 Length", value=cfg.read1_len).classes("flex-1")
            r2_input = ui.number("Read2 Length", value=cfg.read2_len).classes("flex-1")

        with ui.row().classes("justify-end w-full"):
            panel_btn(ui.button("Cancel", on_click=_close_settings_dialog))

            def on_save():
                # update state
                state.flowcell_type = flowcell_select.value
                state.n_lanes = int(lanes_input.value)
                state.lane_capacity_m = int(capacity_input.value)
                state.read1_len = int(r1_input.value)
                state.read2_len = int(r2_input.value)
                state.max_plans = int(max_plans_input.value)
                state.user_name = (user_input.value or "").strip()
                shared_raw = chosen_paths["shared_catalog_dir"]
                state.shared_catalog_dir = Path(shared_raw) if shared_raw else None

                # apply output dir to state
                raw = chosen_paths["output_dir"]
                try:
                    if raw:
                        p = Path(raw)
                        p.mkdir(parents=True, exist_ok=True)
                        state.output_dir = p
                    else:
                        state.output_dir = state.base_dir / "outputs"
                        state.output_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    ui.notify(f"Invalid output folder: {e}. Use default outputs/", type="warning")
                    state.output_dir = state.base_dir / "outputs"
                    state.output_dir.mkdir(parents=True, exist_ok=True)

                # clear current run
                state.reset_run()

                # save config
                new_cfg = RuntimeConfig(
                    flowcell_type=state.flowcell_type,
                    n_lanes=state.n_lanes,
                    lane_capacity_m=state.lane_capacity_m,
                    output_dir=str(state.output_dir), 
                    shared_catalog_dir=str(state.shared_catalog_dir) if state.shared_catalog_dir else None,
                    user_name=state.user_name,
                    read1_len=state.read1_len,
                    read2_len=state.read2_len,
                    max_plans=state.max_plans,
                )
                save_runtime_config(state.base_dir, new_cfg)

                if state.shared_catalog_dir is None:
                    if state.catalog.projects or state.catalog.index_tables.dual or state.catalog.index_tables.single:
                        state.startup_warning = (
                            "Shared catalog is disconnected. The app is using the last loaded projects and indexes in memory only."
                        )
                        ui.notify(state.startup_warning, type="warning")
                    else:
                        state.startup_warning = None
                else:
                    try:
                        state.catalog = load_shared_catalog(state.shared_catalog_dir)
                        state.startup_warning = None
                    except PermissionError as e:
                        state.startup_warning = (
                            f"No permission to read the shared catalog folder: {e}. "
                            'The app is still usable with the last loaded in-memory data. Use "Refresh Shared" after access is restored.'
                        )
                        ui.notify(state.startup_warning, type="negative")
                    except Exception as e:
                        ui.notify(f"Shared catalog load failed: {e}", type="warning")
                state.ensure_valid_project_selection()

                # refresh UI
                refresh_all()

                _close_settings_dialog()

            panel_btn(ui.button("Save", on_click=on_save))

        state.ui_modal_open = True
        dialog.open()

def build_toolbar(state: RunState, refresh_all) -> None:
    """creates a full-width horizontal toolbar for global actions."""
    # A full-width row with vertically centered items and 8px (gap-2) spacing
    with ui.row().classes("w-full items-center gap-2 bg-primary text-white px-3 py-2"):
        ui.label("GRCF SampleSheet Tool").classes("text-lg font-semibold")

        ui.badge(f"v{__version__}").props("outline").classes("text-white border-white/40 ml-2")
        
        if state.has_run_level_error:
            ui.badge(
                "Run-level error",
                color="red"
            ).tooltip(
                "There are validation errors not specific to any lane. "
                "Check the Messages panel for details."
            )

        ui.separator().props("vertical")

        # ---- toolbar button style: visible on dark background ----
        def tb(btn: ui.button):
            btn.props("no-caps unelevated")
            btn.classes(
                "text-white font-medium "
                "bg-white/10 hover:bg-white/18 "
                "border border-white/20 "
                "px-3 py-1.5 "
                "rounded-md "
                "shadow-sm "
                "transition-colors"
            )
            return btn

        tb(ui.button("⚙ Settings", on_click=lambda: open_settings_dialog(state, refresh_all)))
        tb(ui.button("Refresh Shared", on_click=lambda: _refresh_shared_catalog(state, refresh_all)))
        tb(ui.button("Import Project", on_click=lambda: import_project_dialog(state, refresh_all)))
        tb(ui.button("Open Plan", on_click=lambda: open_plan_dialog(state, refresh_all)))
        tb(ui.button("Save Plan", on_click=lambda: do_save_plan(state)))
        tb(ui.button("Validate", on_click=lambda: do_validate(state, refresh_all)))
        tb(ui.button("Summary", on_click=lambda: open_summary_dialog(state)))

        # Export button pushed to the far right using Tailwind's 'ml-auto'
        export_btn = tb(ui.button("Export SampleSheet", on_click=lambda: do_export(state)))
        export_btn.classes("ml-auto")

        # Logic to toggle button availability based on state
        def update_export_enabled():
            if actions.can_export(state):
                export_btn.enable()
            else:
                export_btn.disable()

        update_export_enabled()
        # refresh_all will call update_export_enabled as well, through external parameter


def _refresh_shared_catalog(state: RunState, refresh_all) -> None:
    """Toolbar action for manually reloading the shared catalog."""
    try:
        actions.refresh_shared_catalog(state)
    except Exception as e:
        ui.notify(f"Refresh failed: {e}", type="negative")
        return
    state.startup_warning = None
    ui.notify("Shared catalog refreshed", type="positive")
    refresh_all()


def import_project_dialog(state: RunState, refresh_all) -> None:
    """
    Creates a modal popup (dialog) used for importing a project from CSV/TSV/TXT file.
    """
    with tracked_dialog(state, refresh_all) as dialog, ui.card().classes("w-[520px]"):
        ui.label("Import Project").classes("text-base font-semibold")

        # -------------------------
        # basic metadata
        # -------------------------
        project_id = ui.input("project_id", placeholder="e.g. Gudas-XT-20288").props("autofocus")

        index_type = ui.select(
            options = ["dual", "single"],
            value = "dual",
            label = "index type",
        ).classes("w-full")

        library_type = ui.input(
            "Library type",
            placeholder = "e.g. RNA-seq, scRNA-seq, Amplicon-seq", 
        ).classes("w-full")

        sequencing_type = ui.input(
            "Sequencing type", 
            placeholder = "e.g. PE50+8+8"
        ).classes("w-full")

        required_reads_mode = ui.select(
            options={
                "per_sample": "Per sample",
                "per_project": "Per project", 
            }, 
            value="per_sample", 
            label="Required reads mode", 
        ).classes("w-full")

        default_reads = ui.number(
            "Default required reads per sample (M)",
            value=40,
            min=1,
        ).classes("w-full")

        required_reads_hint = ui.label(
            "Used only when the uploaded file does not provide required_reads_m."
        ).classes("text-xs text-gray-500")

        def _sync_required_reads_ui():
            if required_reads_mode.value == "per_project":
                default_reads.label = "Default required reads per project (M)"
                required_reads_hint.text = (
                    "If the uploaded file does not provide required_reads_m, "
                    "the app will divide the project total by sample count "
                    "and store the result per sample."
                )
            else:
                default_reads.label = "Default required reads per sample (M)"
                required_reads_hint.text = (
                    "Used only when the uploaded file does not provide required_reads_m."
                )
            default_reads.update()

        required_reads_mode.on_value_change(lambda _: _sync_required_reads_ui())
        _sync_required_reads_ui()

        ui.separator()

        # -------------------------
        # file upload
        # -------------------------
        ui.label("Project sample file (CSV/TSV)").classes("text-sm font-semibold")

        uploaded = {
            "path": None,
            "name": None,
        }

        uploader_container = ui.column()

        async def on_upload_project_file(e):
            """
            upload handler.
            e.file is a SpooledTemporaryFile-like object.
            """
            # write uploaded file to a temp path
            content = await e.file.read()

            filename = Path(e.file.name).name
            tmp_path = state.temp_dir / f"_upload_{filename}"

            tmp_path.write_bytes(content)

            uploaded["path"] = str(tmp_path)
            uploaded["name"] = filename

            ui.notify(f"Uploaded: {filename}", type="positive")

        def build_uploader():
            uploader_container.clear()
            ui.upload(
                on_upload = on_upload_project_file, 
                auto_upload = True, 
                multiple = False,
            ).props("accept=.csv,.tsv,.txt")

        build_uploader()

        # -------------------------
        # action buttons
        # -------------------------
        with ui.row().classes("justify-end gap-2 mt-4"):
            panel_btn(ui.button("Cancel", on_click=dialog.close))
            panel_btn(ui.button("Import", on_click=lambda: _do_import()))

        # -------------------------
        # import action
        # ------------------------- 
        def _do_import():
            pid = (project_id.value or "").strip()
            if not pid:
                ui.notify("Project ID is required", type="negative")
                return

            if pid in state.catalog.projects:
                ui.notify(
                    f"Project ID '{pid}' already exists. "
                    "Please use a different Project ID or remove the existing project first.",
                    type="negative",
                    timeout=6000, 
                )
                return

            if not sequencing_type.value:
                ui.notify("Sequencing type is required", type="negative")
                return

            if not uploaded["path"]:
                ui.notify("Please upload a project file", type="negative")
                return

            if default_reads.value is None or int(default_reads.value) <= 0:
                ui.notify("Default required reads must be > 0", type="negative")
                return

            # get temporary file
            tmp_path = Path(uploaded["path"])

            try:
                proj = actions.import_project(
                    state = state,
                    project_id = pid,
                    index_type = index_type.value, 
                    library_type = (library_type.value or "").strip() or None,
                    sequencing_type = (sequencing_type.value or "").strip() or None, 
                    file_path = tmp_path, 
                    default_required_reads_m = int(default_reads.value) if default_reads.value is not None else None, 
                    required_reads_mode=required_reads_mode.value or "per_sample", 
                )
            except Exception as e:
                ui.notify(f"Import failed: {e}", type="negative")
                return
            finally:
                # clean up temporary file
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass

                # reset upload state
                uploaded["path"] = None
                uploaded["name"] = None

            ui.notify(f"Imported project {pid} ({len(proj.samples)} samples)", type="positive")

            # Close the modal and update the main UI
            dialog.close()
            refresh_all()

    dialog.open()


def open_plan_dialog(state: RunState, refresh_all) -> None:
    """creates a modal dialog that allows users to select and load a previously saved configuration file."""
    # Get the default storage directory
    store = state.plan_dir
    # Find up to 30 recent plan JSON files
    plans = sorted(store.glob("plan_*.json"), reverse=True)
    options = [str(p) for p in plans[:30]]

    with tracked_dialog(state, refresh_all) as dialog, ui.card().classes("w-[720px]"):
        ui.label("Open Plan").classes("text-base font-semibold")

        # Handle the case where no plans exist
        if not options:
            ui.label(f"No plans found in {store}")
            panel_btn(ui.button("Close", on_click=dialog.close))
            dialog.open()
            return

        # Display a dropdown list of available plans
        sel = ui.select(options=options, label="Select a saved plan").classes("w-full")

        # Action buttons aligned to the right
        with ui.row().classes("justify-end gap-2"):
            panel_btn(ui.button("Cancel", on_click=dialog.close))
            panel_btn(ui.button("Open", on_click=lambda: _do()))

        def _do():
            # Validation
            if not sel.value:
                ui.notify("Please select a plan", type="warning")
                return

            # Load plan from the selected file
            new_state = load_plan(Path(sel.value))

            # Update the current state with the new data
            state.indexes_panel_collapsed = new_state.indexes_panel_collapsed
            state.indexes_mapping_type = new_state.indexes_mapping_type
            state.messages = new_state.messages

            # sync runtime settings
            state.flowcell_type = new_state.flowcell_type
            state.n_lanes = new_state.n_lanes
            state.lane_capacity_m = new_state.lane_capacity_m
            state.read1_len = new_state.read1_len
            state.read2_len = new_state.read2_len
            state.output_dir = new_state.output_dir
            state.max_plans = new_state.max_plans

            state.selected_project_id = new_state.selected_project_id
            state.lanes = new_state.lanes
            state.samples_rows_per_page = new_state.samples_rows_per_page
            state.assignments = new_state.assignments
            state.selected_sample_uids = new_state.selected_sample_uids
            state.ensure_valid_project_selection()

            # Close dialog and update the UI display
            ui.notify("Plan loaded", type="positive")
            dialog.close()
            refresh_all()

    dialog.open()


def do_save_plan(state: RunState) -> None:
    p = save_plan(state)
    ui.notify(f"Saved: {p}", type="positive")


def do_validate(state: RunState, refresh_all) -> None:
    actions.validate_current_plan(state)
    if state.validation_result:
        if state.validation_result.ok:
            ui.notify("Validation completed OK.", type="positive")
        else:
            ui.notify("Validation failed.", type="negative")
    refresh_all()


def open_summary_dialog(state: RunState) -> None:
    with tracked_dialog(state, lambda: None).props("persistent") as dialog:
        with ui.card().classes("w-[1100px] max-w-full"):
            # ---------- Header ----------
            with ui.row().classes("w-full items-center"):
                ui.label("Summary").classes("text-lg font-semibold")
                panel_btn(ui.button("Close", on_click=dialog.close).classes("ml-auto"))

            ui.separator()

            # ---------- Controls ----------
            with ui.row().classes("w-full items-center gap-4"):
                view_sel = ui.select(
                    options=[
                        "Sample summary",
                        "Assignment detail",
                        "Project summary",
                    ],
                    value="Sample summary",
                    label="View",
                ).classes("w-56")

                proj_opts = ["All"] + sorted(actions.get_projects_in_plan(state))
                project_sel = ui.select(
                    options=proj_opts,
                    value="All",
                    label="Project",
                ).classes("w-56")

            ui.separator()

            # ---------- Content (placeholder for now) ----------
            content = ui.element("div").classes(
                "w-full min-h-[400px] text-sm text-gray-500"
            )

            def render_summary():
                content.clear()

                if view_sel.value == "Sample summary":
                    rows = actions.build_sample_summary_rows(
                        state, 
                        project_filter=project_sel.value or "All", 
                    )
                    with content:
                        ui.table(
                            columns=SAMPLE_SUMMARY_COLUMNS, 
                            rows=rows, 
                            row_key="key", 
                        ).props("dense").classes("w-full") \
                        .add_slot("body-cell-status", r"""
                            <q-td :props="props">
                                <q-chip
                                    dense
                                    size="sm"
                                    :color="{
                                        OK: 'green',
                                        Under: 'blue',
                                        Over: 'orange'
                                    }[props.value]"
                                    text-color="white"
                                >
                                    {{
                                        {
                                            OK: '✓ OK',
                                            Under: '▲ Under',
                                            Over: '● Over'
                                        }[props.value]
                                    }}
                                </q-chip>
                            </q-td>
                        """)
                elif view_sel.value == "Assignment detail":
                    rows = actions.build_assignment_detail_rows(
                        state, 
                        project_filter=project_sel.value or "All",
                    )
                    with content:
                        ui.table(
                            columns=ASSIGNMENT_DETAIL_COLUMNS,
                            rows=rows,
                            row_key="key",
                        ).props("dense").classes("w-full")
                elif view_sel.value == "Project summary":
                    rows = actions.build_project_summary_rows(
                        state, 
                        project_filter=project_sel.value or "All", 
                    )
                    with content:
                        ui.table(
                            columns=PROJECT_SUMMARY_COLUMNS,
                            rows=rows,
                            row_key="key",
                        ).props("dense").classes("w-full")

            # bind refresh
            view_sel.on_value_change(lambda _: render_summary())
            project_sel.on_value_change(lambda _: render_summary())

            # initial render
            render_summary()

    dialog.open()


def do_export(state: RunState) -> None:
    """Export plan to samplesheet files"""
    # force to validate the current plan
    actions.validate_current_plan(state)

    # pre-check
    if not actions.has_any_data(state):
        ui.notify("Cannot export: no samples assigned to any lane", type="warning")
        return
    if not actions.can_export(state):
        ui.notify("Cannot export: Errors present", type="negative")
        return

    with tracked_dialog(state, lambda: None) as dialog, ui.card().classes("w-[520px]"):
        ui.label("Export SampleSheet").classes("text-base font-semibold")

        out_dir = ui.input(
            "Output directory", 
            value=str(state.output_dir), 
        ).classes("w-full")

        prefix = ui.input(
            "File prefix", 
            placeholder="e.g. 20260210_NovaSeq_FCA", 
        ).classes("w-full")

        ui.label("Output format")

        fmt = ui.radio(
            options={
                "basespace": "BaseSpace sequencing plan", 
                "iem": "IEM samplesheet", 
            }, 
            value="basespace", 
        )

        with ui.row().classes("justify-end gap-2 mt-4"):
            panel_btn(ui.button("Cancel", on_click=dialog.close))
            panel_btn(
                ui.button(
                    "Export",
                    on_click=lambda: _do_export_confirm(
                        state, 
                        out_dir.value, 
                        prefix.value, 
                        fmt.value, 
                        dialog, 
                    )
                )
            )

    dialog.open()


def _do_export_confirm(state: RunState, out_dir: str, prefix: str, fmt: str, dialog):
    if not out_dir:
        ui.notify("Output directory is required", type="negative")
        return

    if not prefix:
        ui.notify("File prefix is required", type="negative")
        return

    try:
        paths = actions.export_samplesheets(
            state=state, 
            output_dir=Path(out_dir), 
            prefix=prefix, 
            format=fmt,
        )
    except PlanIntegrityError as e:
        ui.notify(f"Export failed: {e}", type="negative")
        return

    dialog.close()
    ui.notify(f"Exported {len(paths)} file(s)", type="positive")


# -------------------------
# Indexes panel
# -------------------------

def import_mapping_dialog(state: RunState, refresh_all) -> None:
    """Upload a mapping table (CSV/TSV) and merge into the global mapping table."""
    with tracked_dialog(state, refresh_all) as dialog, ui.card().classes("w-[720px]"):
        ui.label("Load mapping table").classes("text-base font-semibold")
        ui.label(
            "Upload CSV/TSV. Comment lines starting with '#' will be ignored. "
            "Then select which columns are ID / i7 / i5 (dual) or ID / sequence (single)."
        ).classes("text-xs text-gray-500")

        mapping_type = ui.select(
            options=["dual","single"],
            value=state.indexes_mapping_type,
            label="Mapping type",
        ).classes("w-full")

        content_preview = ui.textarea("File preview (comments removed)", placeholder="(upload a file)").props("readonly").classes("w-full")
        filename_label = ui.label("").classes("text-xs text-gray-500")

        # simple UI-local buffer
        file_buf: Dict[str, Any] = {"text": "", "name": "", "cols": [], "delimiter": ","}

        # column role selections
        col_id = {"v": None}
        col_i7 = {"v": None} # i7 for dual, sequence for single
        col_i5 = {"v": None}

        ui.separator()

        # ---- column mapping UI (options will be filled after upload) ----
        ui.label("Column mapping").classes("text-subtitle2")

        id_sel = ui.select(options=[], label="Index ID column").classes("w-full")
        seq_sel = ui.select(options=[], label="i7 / sequence column").classes("w-full")
        i5_sel = ui.select(options=[], label="i5 sequence column").classes("w-full")

        # register handlers
        id_sel.on_value_change(lambda e: col_id.__setitem__("v", e.value))
        seq_sel.on_value_change(lambda e: col_i7.__setitem__("v", e.value))
        i5_sel.on_value_change(lambda e: col_i5.__setitem__("v", e.value))

        # show/hide i5 selector based on mapping type
        def _sync_i5_visibility():
            i5_sel.set_visibility(mapping_type.value == "dual")

        mapping_type.on_value_change(lambda _: _sync_i5_visibility())
        _sync_i5_visibility()

        async def on_upload(e):
            out = e.file.read()
            data = await out if inspect.isawaitable(out) else out
            raw = data.decode("utf-8", errors="replace")

            file_buf["name"] = getattr(e, "name", None) or "(uploaded)"
            name_lower = file_buf["name"].lower()

            # determine delimiter from filename
            if name_lower.endswith(".tsv") or name_lower.endswith(".txt"):
                delimiter = "\t"
            else:
                delimiter = ","
            file_buf["delimiter"] = delimiter

            # remove comment lines (start with '#', after stripping)
            lines = raw.splitlines()
            lines = [ln for ln in lines if not ln.lstrip().startswith('#')]

            if not lines:
                ui.notify('No data lines found after removing comments', type='negative')
                return

            clean_text = '\n'.join(lines)
            file_buf['text'] = clean_text

            # parse header columns
            header = [h.strip() for h in lines[0].split(delimiter)]
            file_buf["cols"] = header
            
            # reset selections
            col_id["v"] = None
            col_i7["v"] = None
            col_i5["v"] = None
            id_sel.value = None
            seq_sel.value = None
            i5_sel.value = None

            # update select options
            id_sel.options = header
            seq_sel.options = header
            i5_sel.options = header
            id_sel.update()
            seq_sel.update()
            i5_sel.update()

            filename_label.text = f"Selected: {file_buf['name']}"
            content_preview.value = "\n".join(lines[:20])

        ui.upload(on_upload=on_upload, auto_upload=True, multiple=False).props("accept=.csv,.tsv,.txt")

        ui.separator()

        with ui.row().classes("justify-end gap-2"):
            panel_btn(ui.button("Cancel", on_click=dialog.close))
            panel_btn(ui.button("Load", on_click=lambda: _do()))

        def _do():
            if not file_buf["text"]:
                ui.notify("Please upload a file", type="warning")
                return

            # persist mapping type choice
            state.indexes_mapping_type = mapping_type.value or state.indexes_mapping_type

            # validate column mapping
            if not col_id["v"] or not col_i7["v"]:
                ui.notify("Please select required columns", type="negative")
                return
            if mapping_type.value == "dual" and not col_i5["v"]:
                ui.notify("Please select i5 column for dual mapping", type="negative")
                return

            selected = [col_id["v"], col_i7["v"]]
            if state.indexes_mapping_type== "dual":
                selected.append(col_i5["v"])
            if len(set(selected)) != len(selected):
                ui.notify("Each role must map to a different column", type="negative")
                return

            # rewrite header to internal standard
            lines = file_buf["text"].splitlines()
            delimiter = file_buf["delimiter"]

            header = [h.strip() for h in lines[0].split(delimiter)]

            rename = {
                col_id["v"]: "index_id",
                col_i7["v"]: "i7" if state.indexes_mapping_type == "dual" else "sequence"
            }
            if state.indexes_mapping_type == "dual":
                rename[col_i5["v"]] = "i5"

            new_header = [rename.get(h,h) for h in header]
            lines[0] = delimiter.join(new_header)
            normalized_text = "\n".join(lines)

            ok = actions.import_mapping_table_from_text(
                state,
                state.indexes_mapping_type,
                normalized_text,
                filename=file_buf["name"],
                delimiter=delimiter
            )

            if ok:
                save_plan(state)
                dialog.close()
                refresh_all()
            else:
                # errors already go to Messages Panel
                ui.notify("Mapping table import failed (see Messages)", type="negative")

    dialog.open()


def build_indexes_panel(state: RunState, refresh_all) -> None:
    stats = state.catalog.index_tables.stats()
    total_n = stats["dual_ids"] + stats["single_ids"]

    with ui.card().classes("w-full"):
        # --- header row ---
        header = ui.row().classes("w-full items-center justify-between")

        # local open state (collapsed by default)
        opened = {"v": False}

        with header:
            ui.label(f"Indexes (2 tables, {total_n} IDs)").classes("text-base font-semibold")

            # triangle button on the right ◀ ▶ ▼
            tri = ui.button(
                "▶", on_click=lambda: _toggle()
            ).props("flat dense").classes(
                "text-lg font-semibold"
            ).style("min-width:28px; padding:0 6px;")

        ##ui.separator()

        # --- content ---
        content = ui.element("div").classes("w-full")
        content.set_visibility(False)

        def _toggle():
            opened["v"] = not opened["v"]
            content.set_visibility(opened["v"])
            # shape change: ▼ when expanded, ▶ when collapsed
            tri.text = "▼" if opened["v"] else "▶"

        # Put the real controls inside content
        with content:
            mapping_sel = ui.select(
                options=["dual", "single"],
                value=state.indexes_mapping_type,
                label="Mapping type (dual: index_id,i7,i5 ; single: index_id,sequence)",
            ).classes("w-full")

            def _on_mapping_change(_):
                state.indexes_mapping_type = mapping_sel.value or state.indexes_mapping_type
                save_plan(state)

            mapping_sel.on_value_change(_on_mapping_change)

            ui.separator()

            panel_btn(
                ui.button("Load mapping table…", on_click=lambda: import_mapping_dialog(state, refresh_all)),
            ).classes("w-full")

            ui.label(f"dual: {stats['dual_ids']} IDs | single: {stats['single_ids']} IDs") \
              .classes("text-xs text-gray-500")


# -------------------------
# Projects panel
# -------------------------

def build_project_panel(state: RunState, refresh_all) -> None:
    """Creates a project selection interface that acts as a master-detail controller."""
    _sync_catalog_if_projects_missing(state)
    ui.label("Projects").classes("text-base font-semibold")

    # Safety check for empty state
    if not state.catalog.projects:
        ui.label("No projects imported").classes("text-sm text-gray-500")
        return

    # Build the list of options with metadata
    project_ids = sorted(state.catalog.projects.keys())

    # intialize the selected_project_id so it's non-empty all time
    if state.selected_project_id not in project_ids:
        state.selected_project_id = project_ids[0]

    def _project_label(pid: str):
        p = state.catalog.projects[pid]
        meta = []
        if p.index_type:
            meta.append(p.index_type)
        if p.library_type:
            meta.append(p.library_type)
        if p.sequencing_type:
            meta.append(p.sequencing_type)
        suffix = " | ".join(meta)
        return f"{pid} [{suffix}]" if suffix else pid

    # Create the selection dropdown
    sel = ui.select(
        options={pid: _project_label(pid) for pid in project_ids},
        value=state.selected_project_id,
        label="Select Project",
    ).classes("w-full")

    # Update state and trigger a global UI refresh when selection changes
    def on_change(_):
        state.selected_project_id = sel.value
        refresh_all()

    sel.on_value_change(on_change)

    p = state.catalog.projects[state.selected_project_id]

    with ui.row().classes("w-full items-center gap-2"):
        ui.label(f"Samples: {p.n_samples}").classes("text-xs text-gray-600")
        if p.total_required_reads_m is not None:
            ui.label(f"Total reads(M): {p.total_required_reads_m}").classes("text-xs text-gray-600")

        panel_btn(
            ui.button("Remove", on_click=lambda: _confirm_remove_project(state, refresh_all)), 
        ).classes("ml-auto")

    ## debug
    ##ui.label(f"DEBUG pid={state.selected_project_id} projects={list(state.catalog.projects.keys())}").classes("text-xs text-gray-500")
    ##ui.label(f"Selected: {state.selected_project_id}").classes("text-xs text-gray-500")

def _confirm_remove_project(state: RunState, refresh_all):
    pid = state.selected_project_id
    if not pid:
        return

    with tracked_dialog(state, refresh_all) as dlg, ui.card():
        ui.label(f"Remove project '{pid}'?").classes("font-semibold")
        ##ui.label("This will remove the project and all its lane assignments.").classes("text-sm")
        ui.label("This will remove the project from the Projects Panel.").classes("text-sm")

        with ui.row().classes("justify-end gap-2"):
            panel_btn(ui.button("Cancel", on_click=dlg.close))
            panel_btn(ui.button("Remove", on_click=lambda: _do_remove_project(state, pid, dlg, refresh_all)))

    dlg.open()

def _do_remove_project(state: RunState, pid: str, dlg, refresh_all):
    actions.remove_project(state, pid)
    dlg.close()
    refresh_all()


# -------------------------
# Samples panel
# -------------------------

def build_sample_panel(state: RunState, refresh_all) -> None:
    """creates a data-rich panel that displays samples in a table and allows users to assign them to sequencing lanes."""
    ui.label("Samples").classes("text-base font-semibold")

    # Safety check: ensure a project is actually selected
    pid = state.selected_project_id
    if not pid or pid not in state.catalog.projects:
        ui.label("Select a project to view samples").classes("text-sm text-gray-500")
        return

    # Prepare table rows
    p = state.catalog.projects[pid]
    ##ui.label(f"DEBUG samples={len(p.samples)}").classes("text-xs text-gray-500") # DEBUG

    # get index type of the current project
    index_type = p.index_type if p else "dual"

    rows: List[Dict[str, Any]] = []
    for s in p.samples:
        rows.append({
            "sample_uid": make_sample_uid(s.project_id, s.sample_id), 
            "project_id": s.project_id, 
            "sample_id": s.sample_id,
            "i7_id": s.i7_id,
            "i7_seq": s.i7_seq,
            "i5_id": s.i5_id,
            "i5_seq": s.i5_seq,
            "required_reads_m": s.required_reads_m,
        })
    ##ui.label(f"DEBUG rows={len(rows)}").classes("text-xs text-gray-500") # DEBUG

    columns = [
        {"name": "sample_id", "label": "Sample ID", "field": "sample_id", "sortable": True},
        {"name": "i7_id", "label": "i7 ID", "field": "i7_id", "sortable": True}, 
        {"name": "i7_seq", "label": "i7 Seq", "field": "i7_seq", "sortable": True}, 
    ]
    ##ui.label("DEBUG sample id of first sample: {}".format(rows[0]["sample_id"])) # DEBUG

    if index_type == "dual":
        columns += [
            {"name": "i5_id", "label": "i5 ID", "field": "i5_id", "sortable": True}, 
            {"name": "i5_seq", "label": "i5 Seq", "field": "i5_seq", "sortable": True}, 
        ]

    columns += [
        {"name": "required_reads_m", "label": "Required Reads (M)", "field": "required_reads_m", "sortable": True},
    ]

    # Table container enforces X/Y-scroll and prevents global page scroll + table fill width
    with ui.element("div").classes("w-full").style("overflow:auto; max-height: 68vh; width: 100%;"):
        table = ui.table(
            columns=columns,
            rows=rows,
            row_key="sample_uid",
            selection="multiple",
            pagination={"rowsPerPage": state.samples_rows_per_page},
        ).classes("w-full")

        # Critical: force QTable to expand to container width even if columns are few
        table.props('table-style="width: 100%;"')
        # Make the table itself width:100% too (covers some NiceGUI/Quasar combos)
        table.style("white-space: nowrap; width: 100%;")
        ##table.style("width: 100%;")

    table.props("dense")
    table.props("flat")
    table.props(":rows-per-page-options=\"[20,40,60,80,100]\"")
    # wrap-cells=false sometimes makes table prefer content width; keep but it's ok with table-style=100%
    table.props("wrap-cells=false")

    # Update rows per page in RunState
    def on_pagination(e):
        pag = None
        # NiceGUI event payload may be in e.args or e.pagination depending on version
        if hasattr(e, "args"):
            pag = e.args
        elif hasattr(e, "pagination"):
            pag = e.pagination

        if isinstance(pag, dict) and "rowsPerPage" in pag:
            state.samples_rows_per_page = int(pag["rowsPerPage"])

    table.on("update:pagination", on_pagination)

    # --- Selection helpers (project-wide, not page-limited) ---
    selected_count = ui.label("Selected: 0").classes("text-xs text-gray-500")

    def _update_selected_count():
        selected = table.selected or []
        selected_count.text = f"Selected: {len(selected)}"

    def _select_all(checked: bool):
        # When checked: select ALL rows in this project (even across pages)
        table.selected = rows if checked else []
        _update_selected_count()

    # Optional: keep the count updated when user manually ticks checkboxes on the current page
    # (This depends on NiceGUI version; using a safe trigger by reading table.selected)
    table.on('selection', lambda _: _update_selected_count())

    with ui.row().classes("items-center gap-3"):
        # A real "select all in project" control (not the table header checkbox)
        select_all_cb = ui.checkbox(f"Select all samples in project ({len(rows)})", value=False)
        select_all_cb.on_value_change(lambda e: _select_all(e.value))

        panel_btn(ui.button("Clear selection", on_click=lambda: _select_all(False)))

    # Control row for adding samples to lane(s)
    with ui.row().classes("items-center gap-2"):
        lane_sel = ui.select(
            options=[str(i) for i in range(1, state.n_lanes + 1)],
            label="Add to lane(s)",
            multiple=True,
        ).classes("w-64")

        planned_reads = ui.number(
            "Reads per lane (M)",
            min=10,
            step=10,
        ).classes("w-56")

        @invalidate_validation(state)
        def do_add():
            selected = table.selected or []
            sample_uids = [r["sample_uid"] for r in selected]
            lane_ids = [int(x) for x in (lane_sel.value or [])]

            # Validation toasts:
            if not sample_uids:
                ui.notify("No samples selected", type="warning")
                return
            if not lane_ids:
                ui.notify("No lanes selected", type="warning")
                return
            if planned_reads.value is None or int(planned_reads.value) <= 0:
                ui.notify("Reads per lane (M) must be > 0", type="warning")
                return

            # Persist changes
            try:
                actions.assign_samples_to_lanes(state, sample_uids, lane_ids, int(planned_reads.value))
            except Exception as e:
                ui.notify(f"Assign failed: {e}", type="negative")
                return

            # Clear selection
            table.selected = []
            select_all_cb.value = False
            _update_selected_count()

            refresh_all()

        panel_btn(ui.button("Add selected", on_click=do_add))


# -------------------------
# Lanes panel (dense summary)
# -------------------------

def build_lane_panel(state: RunState, refresh_all) -> None:
    """creates a monitoring and management panel for sequencing lanes."""
    ui.label("Lanes").classes("text-base font-semibold")

    # Dense layout: fixed left column for status dot
    for lid in range(1, state.n_lanes + 1):
        lane = state.lanes[lid]

        def make_on_remove_project(lid: int):
            @invalidate_validation(state)
            def handler(pid: str):
                _rm_project(state, lid, pid, refresh_all)
            return handler

        _on_remove_project = make_on_remove_project(lid)

        def make_on_clear_lane(lid: int):
            @invalidate_validation(state)
            def handler():
                _clear_lane(state, lid, refresh_all)
            return handler
        _on_clear_lane = make_on_clear_lane(lid)

        with ui.card().classes("w-full mb-2"):
            used = lane_used_reads_m(state, lid)
            capacity = state.lane_capacity_m
            pct = used / capacity if capacity > 0 else 0

            # ---------- Line 1: status + lane + reads + progress ----------
            with ui.row().classes("w-full items-center gap-2"):
                # status dot (left, highest priority)
                ui.label(status_dot(lane.status))

                # Lane label
                ui.label(f"Lane {lid}").classes("font-semibold")

                # right-side info group (reads summary)
                with ui.row().classes("items-center gap-2 ml-auto"):
                    # text (main info)
                    ui.label(
                        f"{used} / {capacity} M reads"
                    ).classes("text-sm text-gray-700")

                    # progress bar (right-aligned, short)
                    ui.linear_progress(
                        value=min(pct, 1.0),
                        color="red" if pct >= 1.0 else "primary",
                    ).props("show-value=false").classes("w-16")

            # ---------- Line 2: projects / samples info + CLEAR LANE ----------
            with ui.row().classes("w-full items-center mt-0"):
                ui.label(
                    f"projects: {len(lane.project_ids)}   samples: {len(lane.sample_uids)}"
                ).classes("text-sm text-gray-600 leading-tight")

                panel_btn(ui.button("Clear lane", on_click=_on_clear_lane)).classes("ml-auto")

            # ---------- Actions ----------
            with ui.row().classes("items-center gap-2 mt-1"):
                # local buffer to store selected project
                rm_selected = {"pid": None}

                rm_sel = ui.select(
                    options=lane.project_ids,
                    label="Remove project(s)",
                ).classes("w-56")

                # freeze rm_selected for this lane
                rm_sel.on_value_change(lambda e, _buf=rm_selected: _buf.__setitem__("pid", e.value))

                # freeze handler + buffer for this lane
                panel_btn(
                    ui.button("Remove", on_click=lambda _h=_on_remove_project, _buf=rm_selected: _h(_buf["pid"])), 
                )


def _rm_project(state: RunState, lane_id: int, project_id: str | None, refresh_all) -> None:
    """Remove projects from a lane."""
    ###ui.notify(f"Removing project {project_id} from lane {lane_id}", type="info") # debug only
    # Guard against empty selection
    if not project_id:
        ui.notify("Select a project to remove", type="warning")
        return

    # Update state
    actions.remove_project_from_lane(state, lane_id, project_id)

    # Automatically save plan
    save_plan(state)

    # Trigger UI update
    refresh_all()


def _clear_lane(state: RunState, lane_id: int, refresh_all) -> None:
    """Wipe all data for a lane."""
    # Update state
    actions.clear_lane(state, lane_id)

    # Automatically save plan
    save_plan(state)

    # Trigger UI update
    refresh_all()


# -------------------------
# Messages panel
# -------------------------

def build_messages_panel(state: RunState, refresh_all) -> None:
    with ui.card().classes("w-full h-full").style("overflow:hidden;"):
        ui.label("Messages").classes("text-base font-semibold")

        # Only show warnings/errors (by model), persistent
        msgs = list(state.messages)

        if not msgs:
            ui.label("No errors or warnings").classes("text-sm text-gray-500")
            return

        # Controls
        with ui.row().classes("w-full items-center gap-2"):
            search = ui.input("Search", placeholder="text contains...").classes("w-full")
            lane_opts = ["(any)"] + [str(i) for i in range(1, state.n_lanes + 1)]
            lane_sel = ui.select(options=lane_opts, value="(any)", label="Lane").classes("w-28")

            proj_opts = ["(any)"] + sorted(state.catalog.projects.keys())
            proj_sel = ui.select(options=proj_opts, value="(any)", label="Project").classes("w-40")

            panel_btn(ui.button("Clear index import msgs", on_click=lambda: _clear_source("index_import")))

        def _clear_source(src: str):
            actions.clear_messages(state, source=src)
            save_plan(state)
            refresh_all()

        # Filter function
        def _filtered() -> List[Message]:
            q = (search.value or "").strip().lower()
            lane_v = lane_sel.value
            proj_v = proj_sel.value

            out: List[Message] = []
            for m in msgs:
                if lane_v != "(any)":
                    if m.lane is None or str(m.lane) != lane_v:
                        continue
                if proj_v != "(any)":
                    if (m.project_id or "") != proj_v:
                        continue
                if q:
                    hay = " ".join([m.level, m.source, m.text, str(m.lane or ""), m.project_id or "", m.sample_id or ""]).lower()
                    if q not in hay:
                        continue
                out.append(m)
            return out

        columns = [
            {"name": "level", "label": "level", "field": "level", "sortable": True},
            {"name": "source", "label": "source", "field": "source", "sortable": True},
            {"name": "lane", "label": "lane", "field": "lane", "sortable": True},
            {"name": "project", "label": "project", "field": "project", "sortable": True},
            {"name": "sample", "label": "sample", "field": "sample", "sortable": True},
            {"name": "text", "label": "message", "field": "text"},
            {"name": "ts", "label": "time", "field": "ts", "sortable": True},
        ]

        def _rows() -> List[Dict[str, Any]]:
            out = []
            for m in _filtered():
                out.append(
                    {
                        "level": m.level,
                        "source": m.source,
                        "lane": m.lane or "",
                        "project": m.project_id or "",
                        "sample": m.sample_id or "",
                        "text": m.text,
                        "ts": m.ts,
                    }
                )
            # newest last keeps context; user can sort by time if needed
            return out

        # table area: x/y scroll container (critical fix)
        # Keep header+controls fixed, only table scrolls
        table_container = ui.element("div").classes("w-full").style(
            "overflow:auto; height: calc(100% - 96px);"  # 96px roughly for title+filters row
        )

        def _render_table():
            table_container.clear()
            with table_container:
                t = ui.table(columns=columns, rows=_rows(), row_key="ts").props("dense").classes("w-full")
                # keep cells from wrapping so horizontal scroll works
                t.style("white-space: nowrap; width: 100%;")

        # Re-render when controls change
        search.on_value_change(lambda _: _render_table())
        lane_sel.on_value_change(lambda _: _render_table())
        proj_sel.on_value_change(lambda _: _render_table())

        _render_table()


# -------------------------
# main layout
# -------------------------

def build_main_view(state: RunState) -> None:
    """
    Root coordinator for application's layout.
    Three-column layout + toolbar. Rebuild on refresh.
    """
    ui.colors(
        primary="#2C3E50",
        secondary="#34495E",
        accent="#16A085",
        positive="#2E8B57",
        negative="#E74C3C",
        warning="#B7791F",
    )
    ui.add_head_html("""
        <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial; }
        </style>
    """)
    # Create a persistent outer container
    container = ui.column().classes("w-full h-screen overflow-hidden")

    def _dismiss_startup_warning() -> None:
        """Hide the current startup banner for the active session."""
        state.startup_warning = None
        refresh_all()

    # Define how to completely redraw the UI
    def refresh_all():
        # Wipes every existing UI element inside the main column
        container.clear()
        with container:
            # Top section
            build_toolbar(state, refresh_all)

            if state.startup_warning:
                with ui.row().classes(
                    "w-full items-center gap-3 px-4 py-3 bg-amber-100 text-amber-900 border-b border-amber-300"
                ):
                    ui.icon("warning").classes("text-lg")
                    ui.label(state.startup_warning).classes("text-sm")
                    ui.button(
                        "Dismiss",
                        on_click=lambda: _dismiss_startup_warning(),
                    ).props("flat dense no-caps").classes("ml-auto text-amber-900")

            ui.separator()

            # Main body: Three-column layout
            with ui.row().classes("w-full h-[calc(100vh-64px)] overflow-hidden no-wrap"):
                # Left column: Indexes + Projects + Messages
                with ui.column().classes("w-1/4 h-full overflow-hidden gap-2"):
                    # Indexes: natural height, collapse will really shrink
                    with ui.element("div").classes("w-full"):
                        build_indexes_panel(state, refresh_all)
                    # Projects: natural height
                    with ui.element("div").classes("w-full"):
                        with ui.card().classes("w-full"):
                            build_project_panel(state, refresh_all)
                    # Messages: take remaining height (this is the key)
                    with ui.element("div").classes("w-full flex-1 overflow-hidden"):
                        build_messages_panel(state, refresh_all)

                # Center column: Samples Table (x/y scroll)
                with ui.column().classes("w-2/4 h-full overflow-hidden"):
                    with ui.card().classes("w-full h-full overflow-hidden"):
                        with ui.element("div").classes("w-full h-full overflow-auto"):
                            build_sample_panel(state, refresh_all)

                # Right column: Lanes (y scroll)
                with ui.column().classes("w-1/4 h-full overflow-hidden"):
                    with ui.card().classes("w-full h-full overflow-hidden"):
                        with ui.element("div").classes("w-full h-full overflow-auto"):
                            build_lane_panel(state, refresh_all)

    # Initial render
    refresh_all()
    ui.timer(
        max(1, int(state.shared_catalog_poll_seconds)),
        lambda: _run_safe_ui_background_task(
            state,
            refresh_all,
            lambda: _background_refresh_shared_catalog(state, refresh_all),
            "Shared catalog background refresh",
        ),
    )
    ui.timer(
        1.0,
        lambda: _run_safe_ui_background_task(
            state,
            refresh_all,
            lambda: _flush_pending_project_refresh(state, refresh_all),
            "Deferred UI refresh",
        ),
    )
