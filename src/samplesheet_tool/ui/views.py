# views.py
# UI appearance
# 

from __future__ import annotations
from nicegui import ui
from typing import List, Dict, Any
from samplesheet_tool.ui.state import RunState, LaneStatus, save_plan, load_plan, default_store_dir
from samplesheet_tool.ui import actions
from pathlib import Path


def status_dot(status: LaneStatus) -> str:
    return {
        LaneStatus.OK: "🟢",
        LaneStatus.WARNING: "🟠",
        LaneStatus.ERROR: "🔴",
    }[status]


def build_toolbar(state: RunState, refresh_all) -> None:
    """creates a full-width horizontal toolbar that manages application state (such as the "Index Set") and triggers global UI refreshes."""
    # A full-width row with vertically centered items and 8px (gap-2) spacing
    with ui.row().classes("w-full items-center gap-2"):
        ui.label("SampleSheet Tool (UI MVP)").classes("text-lg font-semibold")

        ui.separator().props("vertical")

        # Dropdown for selecting the index set
        index_set = ui.select(
            options=["Illumina (mock)", "10x (mock)"],
            value=state.index_set_name,
            label="Index Set",
        ).classes("w-56")

        # Updates state and triggers a refresh of the UI parts
        def on_index_set_change(e):
            state.index_set_name = e.value
            refresh_all()

        # Listen for value changes in the selection
        index_set.on_value_change(on_index_set_change)

        # Standard action buttons
        ui.button("Import Project", on_click=lambda: import_project_dialog(state, refresh_all))
        ui.button("Open Plan", on_click=lambda: open_plan_dialog(state, refresh_all))
        ui.button("Save Plan", on_click=lambda: do_save_plan(state))
        ui.button("Validate", on_click=lambda: do_validate(state, refresh_all))

        # Export button pushed to the far right using Tailwind's 'ml-auto'
        export_btn = ui.button("Export SampleSheet", on_click=lambda: do_export(state))
        export_btn.classes("ml-auto")

        # Logic to toggle button availability based on state
        def update_export_enabled():
            if actions.can_export(state):
                export_btn.enable()
            else:
                export_btn.disable()

        update_export_enabled()
        # refresh_all will call update_export_enabled as well, through external parameter


def import_project_dialog(state: RunState, refresh_all) -> None:
    """creates a modal popup (dialog) used for entering project data"""
    with ui.dialog() as dialog, ui.card().classes("w-[520px]"):
        ui.label("Import Project (mock)").classes("text-base font-semibold")

        # User input fields
        project_id = ui.input("project_id", placeholder="e.g. 15730").props("autofocus")
        n = ui.number("n_samples", value=12, min=1, max=200)

        # Action buttons aligned to the right
        with ui.row().classes("justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Import", on_click=lambda: _do()).props("unelevated")

        def _do():
            # Basic validation
            pid = (project_id.value or "").strip()
            if not pid:
                ui.notify("project_id is required", type="negative")
                return

            # Excute mock backend action (assumes an 'actions' module exists)
            # replace it with real import + atomic validate later
            actions.mock_import_project(state, pid, int(n.value or 12))

            # Close the modal and update the main UI
            dialog.close()
            refresh_all()

    dialog.open()


def open_plan_dialog(state: RunState, refresh_all) -> None:
    """creates a modal dialog that allows users to select and load a previously saved configuration file."""
    # Get the default storage directory
    store = default_store_dir()
    # Find up to 30 recent plan JSON files
    plans = sorted(store.glob("plan_*.json"), reverse=True)
    options = [str(p) for p in plans[:30]]

    with ui.dialog() as dialog, ui.card().classes("w-[720px]"):
        ui.label("Open Plan").classes("text-base font-semibold")

        # Handle the case where no plans exist
        if not options:
            ui.label(f"No plans found in {store}")
            ui.button("Close", on_click=dialog.close)
            dialog.open()
            return

        # Display a dropdown list of available plans
        sel = ui.select(options=options, label="Select a saved plan").classes("w-full")

        # Action buttons aligned to the right
        with ui.row().classes("justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Open", on_click=lambda: _do()).props("unelevated")

        def _do():
            # Validation
            if not sel.value:
                ui.notify("Please select a plan", type="warning")
                return

            # Load plan from the selected file
            new_state = load_plan(Path(sel.value))

            # Update the current state with the new data
            state.index_set_name = new_state.index_set_name
            state.projects = new_state.projects
            state.selected_project_id = new_state.selected_project_id
            state.lanes = new_state.lanes

            # Close dialog and update the UI display
            dialog.close()
            refresh_all()

    dialog.open()


def do_save_plan(state: RunState) -> None:
    p = save_plan(state)
    ui.notify(f"Saved: {p}", type="positive")


def do_validate(state: RunState, refresh_all) -> None:
    actions.validate_full_mock(state)
    ui.notify("Validation finished (mock)", type="positive")
    refresh_all()


def do_export(state: RunState) -> None:
    actions.validate_full_mock(state)
    if not actions.has_any_data(state):
        ui.notify("Cannot export: no samples assigned to any lane", type="warning")
        return
    if not actions.can_export(state):
        ui.notify("Cannot export: Errors present (mock)", type="negative")
        return
    ui.notify("Exported SampleSheet (mock)", type="positive")


def build_project_panel(state: RunState, refresh_all) -> None:
    """Creates a project selection interface that acts as a master-detail controller."""
    ui.label("Projects").classes("text-base font-semibold")

    # Safety check for empty state
    if not state.projects:
        ui.label("No projects imported").classes("text-sm text-gray-500")
        return

    # Build the list of options with metadata
    project_ids = sorted(state.projects.keys())

    # intialize the selected_project_id so it's non-empty all time
    if state.selected_project_id not in project_ids:
        state.selected_project_id = project_ids[0]

    # Create the selection dropdown
    sel = ui.select(
        options=project_ids,
        value=state.selected_project_id,
        label="Select Project",
    ).classes("w-full")

    # Update state and trigger a global UI refresh when selection changes
    def on_change(_):
        state.selected_project_id = sel.value
        refresh_all()

    sel.on_value_change(on_change)

    # debug
    ui.label(f"DEBUG pid={state.selected_project_id} projects={list(state.projects.keys())}").classes("text-xs text-gray-500")
    ui.label(f"Selected: {state.selected_project_id}").classes("text-xs text-gray-500")


def build_sample_panel(state: RunState, refresh_all) -> None:
    """creates a data-rich panel that displays samples in a table and allows users to assign them to sequencing lanes."""
    ui.label("Samples").classes("text-base font-semibold")

    # Safety check: ensure a project is actually selected
    pid = state.selected_project_id
    if not pid or pid not in state.projects:
        ui.label("Select a project to view samples").classes("text-sm text-gray-500")
        return

    # Prepare table rows
    p = state.projects[pid]
    ui.label(f"DEBUG samples={len(p.samples)}").classes("text-xs text-gray-500") # DEBUG
    rows = []
    for s in p.samples:
        rows.append({
            "sample_id": s.sample_id,
            "reads_m": s.reads_m,
            "index_id": s.index_id,
        })
    ui.label(f"DEBUG rows={len(rows)}").classes("text-xs text-gray-500") # DEBUG

    columns = [
        {"name": "sample_id", "label": "sample_id", "field": "sample_id", "sortable": True},
        {"name": "reads_m", "label": "reads(M)", "field": "reads_m", "sortable": True},
        {"name": "index_id", "label": "index_id", "field": "index_id", "sortable": True},
    ]

    ui.label("DEBUG sample id of first sample: {}".format(rows[0]["sample_id"])) # DEBUG
    # Create the interactive table
    table = ui.table(
        columns=columns, 
        rows=rows, 
        row_key="sample_id", 
        selection="multiple", 
        pagination={"rowsPerPage": state.samples_rows_per_page}
    ).classes("w-full")

    table.props('dense')
    table.props(':rows-per-page-options="[25,50,100]"')

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

    with ui.row().classes("items-center gap-3"):
        # A real "select all in project" control (not the table header checkbox)
        select_all_cb = ui.checkbox(f"Select all samples in project ({len(rows)})", value=False)
        select_all_cb.on_value_change(lambda e: _select_all(e.value))

        ui.button("Clear selection", on_click=lambda: _select_all(False)).props("flat")

    # Optional: keep the count updated when user manually ticks checkboxes on the current page
    # (This depends on NiceGUI version; using a safe trigger by reading table.selected)
    table.on('selection', lambda _: _update_selected_count())

    # Control row for adding samples to lane(s)
    with ui.row().classes("items-center gap-2"):
        lane_sel = ui.select(
            options=[str(i) for i in range(1, 9)],
            label="Add to lane(s)",
            multiple=True,
        ).classes("w-64")

        def do_add():
            selected = table.selected or []
            sample_ids = [r["sample_id"] for r in selected]
            lane_ids = [int(x) for x in (lane_sel.value or [])]

            # Validation toasts:
            if not sample_ids:
                ui.notify("No samples selected", type="warning")
                return
            if not lane_ids:
                ui.notify("No lanes selected", type="warning")
                return

            # Persist changes
            actions.add_samples_to_lanes(state, sample_ids, lane_ids)
            save_plan(state)  # auto-save after lane change
            table.selected = []
            select_all_cb.value = False
            _update_selected_count()
            refresh_all()

        ui.button("Add selected", on_click=do_add)


def build_lane_panel(state: RunState, refresh_all) -> None:
    """creates a monitoring and management panel for sequencing lanes."""
    ui.label("Lanes").classes("text-base font-semibold")

    for lid in range(1, 9):
        lane = state.lanes[lid]
        with ui.card().classes("w-full mb-2"):
            # Header row with Lane ID and Status indicator
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Lane {lid}").classes("font-semibold")
                ui.label(status_dot(lane.status))

            # Metadata summary
            ui.label(f"projects: {len(lane.project_ids)}  ·  samples: {len(lane.sample_ids)}").classes("text-sm")

            # Error handling: displays error text and a collapsible details selection
            if lane.status == LaneStatus.ERROR:
                ui.label(lane.headline or "Error").classes("text-sm font-semibold text-red-600")
                if lane.details:
                    with ui.expansion("details").classes("w-full"):
                        for d in lane.details[:5]: # Show first 5 errors
                            ui.label(d).classes("text-xs text-gray-700")

            # Management actions
            with ui.row().classes("items-center gap-2 mt-2"):
                rm_sel = ui.select(
                    options=lane.project_ids,
                    label="Remove project(s)",
                ).classes("w-56")

                ui.button(
                    "Remove",
                    on_click=lambda l=lid, s=rm_sel: _rm_project(state, l, s.value, refresh_all),
                ).props("outline")

                ui.button(
                    "Clear lane",
                    on_click=lambda l=lid: _clear_lane(state, l, refresh_all),
                ).props("outline")


def _rm_project(state: RunState, lane_id: int, project_id: str | None, refresh_all) -> None:
    """Remove projects from a lane."""
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


def build_main_view(state: RunState) -> None:
    """
    Root coordinator for application's layout.
    Three-column layout + toolbar. Rebuild on refresh.
    """
    # Create a persistent outer container
    container = ui.column().classes("w-full")

    # Define how to completely redraw the UI
    def refresh_all():
        # Wipes every existing UI element inside the main column
        container.clear()
        with container:
            # Top section
            build_toolbar(state, refresh_all)

            ui.separator()

            # Main body: Three-column layout
            with ui.row().classes("w-full no-wrap"):
                # Left: Projects (25%)
                with ui.column().classes("col-3"):
                    with ui.card().classes("w-full"):
                        build_project_panel(state, refresh_all)

                # Center: Samples Table (50%)
                with ui.column().classes("col-6"):
                    with ui.card().classes("w-full"):
                        build_sample_panel(state, refresh_all)

                # Right: Lanes/Status (25%)
                with ui.column().classes("col-3"):
                    with ui.card().classes("w-full"):
                        build_lane_panel(state, refresh_all)

    # Initial render
    refresh_all()

