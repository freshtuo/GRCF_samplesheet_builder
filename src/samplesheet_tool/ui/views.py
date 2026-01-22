# views.py
# UI appearance
# 

from __future__ import annotations

import inspect
from nicegui import ui
from typing import List, Dict, Any, Optional
from pathlib import Path

from samplesheet_tool.ui.state import (
    RunState, LaneStatus, Message, 
    save_plan, load_plan, default_store_dir, 
    make_sample_uid, split_sample_uid, 
)
from samplesheet_tool.ui import actions

# -------------------------
# small helpers
# -------------------------

def status_dot(status: LaneStatus) -> str:
    return {
        LaneStatus.OK: "🟢",
        LaneStatus.WARNING: "🟠",
        LaneStatus.ERROR: "🔴",
    }[status]


# -------------------------
# toolbar
# -------------------------

def build_toolbar(state: RunState, refresh_all) -> None:
    """creates a full-width horizontal toolbar for global actions."""
    # A full-width row with vertically centered items and 8px (gap-2) spacing
    with ui.row().classes("w-full items-center gap-2"):
        ui.label("SampleSheet Tool (UI MVP)").classes("text-lg font-semibold")

        ui.separator().props("vertical")

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
    """
    Creates a modal popup (dialog) used for entering project data
    Mock project import dialog (atomic import later when wired to CLI).
    """
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
            state.index_tables = new_state.index_tables
            state.indexes_panel_collapsed = new_state.indexes_panel_collapsed
            state.indexes_mapping_type = new_state.indexes_mapping_type
            state.messages = new_state.messages
            state.projects = new_state.projects
            state.selected_project_id = new_state.selected_project_id
            state.lanes = new_state.lanes
            state.samples_rows_per_page = new_state.samples_rows_per_page

            # Close dialog and update the UI display
            ui.notify("Plan loaded", type="positive")
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


# -------------------------
# Indexes panel
# -------------------------

def import_mapping_dialog(state: RunState, refresh_all) -> None:
    """Upload a mapping table (CSV/TSV) and merge into the global mapping table."""
    with ui.dialog() as dialog, ui.card().classes("w-[720px]"):
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
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Load", on_click=lambda: _do()).props("unelevated")

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
    stats = state.index_tables.stats()
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

            ui.button(
                "Load mapping table…",
                on_click=lambda: import_mapping_dialog(state, refresh_all),
            ).props("outline").classes("w-full")

            ui.label(f"dual: {stats['dual_ids']} IDs | single: {stats['single_ids']} IDs") \
              .classes("text-xs text-gray-500")


# -------------------------
# Projects panel
# -------------------------

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

    p = state.projects[state.selected_project_id]
    ui.label(f"Samples: {p.n_samples}").classes("text-xs text-gray-600")
    if p.total_reads_m is not None:
        ui.label(f"Total reads(M): {p.total_reads_m}").classes("text-xs text-gray-600")

    ## debug
    ##ui.label(f"DEBUG pid={state.selected_project_id} projects={list(state.projects.keys())}").classes("text-xs text-gray-500")
    ##ui.label(f"Selected: {state.selected_project_id}").classes("text-xs text-gray-500")


# -------------------------
# Samples panel
# -------------------------

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
    ##ui.label(f"DEBUG samples={len(p.samples)}").classes("text-xs text-gray-500") # DEBUG

    rows: List[Dict[str, Any]] = []
    for s in p.samples:
        rows.append({
            "sample_uid": make_sample_uid(s.project_id, s.sample_id), 
            "project_id": s.project_id, 
            "sample_id": s.sample_id,
            "reads_m": s.reads_m,
            "index_id": s.index_id,
        })
    ##ui.label(f"DEBUG rows={len(rows)}").classes("text-xs text-gray-500") # DEBUG

    columns = [
        {"name": "sample_id", "label": "sample_id", "field": "sample_id", "sortable": True},
        {"name": "reads_m", "label": "reads(M)", "field": "reads_m", "sortable": True},
        {"name": "index_id", "label": "index_id", "field": "index_id", "sortable": True},
    ]
    ##ui.label("DEBUG sample id of first sample: {}".format(rows[0]["sample_id"])) # DEBUG

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

        ui.button("Clear selection", on_click=lambda: _select_all(False)).props("flat")

    # Control row for adding samples to lane(s)
    with ui.row().classes("items-center gap-2"):
        lane_sel = ui.select(
            options=[str(i) for i in range(1, 9)],
            label="Add to lane(s)",
            multiple=True,
        ).classes("w-64")

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

            # Persist changes
            actions.add_samples_to_lanes(state, sample_uids, lane_ids)
            save_plan(state)  # auto-save after lane change

            # Clear selection
            table.selected = []
            select_all_cb.value = False
            _update_selected_count()

            refresh_all()

        ui.button("Add selected", on_click=do_add)


# -------------------------
# Lanes panel (dense summary)
# -------------------------

def build_lane_panel(state: RunState, refresh_all) -> None:
    """creates a monitoring and management panel for sequencing lanes."""
    ui.label("Lanes").classes("text-base font-semibold")

    # Dense layout: fixed right column for status dot
    for lid in range(1, 9):
        lane = state.lanes[lid]

        with ui.card().classes("w-full mb-2"):
            with ui.row().classes("w-full items-center"):
                # Left
                ui.label(f"Lane {lid}").classes("font-semibold")

                # Middle summary
                ui.label(
                    f"projects: {len(lane.project_ids)}   samples: {len(lane.sample_uids)}"
                ).classes("text-sm text-gray-700")

                # Right-aligned status dot (fixed)
                ui.label(status_dot(lane.status)).classes("ml-auto")

            # Brief summary only (details go to Messages Panel)
            if lane.status != LaneStatus.OK and lane.headline:
                ui.label(lane.headline).classes("text-xs text-gray-700")

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
            lane_opts = ["(any)"] + [str(i) for i in range(1, 9)]
            lane_sel = ui.select(options=lane_opts, value="(any)", label="Lane").classes("w-28")

            proj_opts = ["(any)"] + sorted(state.projects.keys())
            proj_sel = ui.select(options=proj_opts, value="(any)", label="Project").classes("w-40")

            ui.button("Clear index import msgs", on_click=lambda: _clear_source("index_import")).props("flat")

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
    # Create a persistent outer container
    container = ui.column().classes("w-full h-screen overflow-hidden")

    # Define how to completely redraw the UI
    def refresh_all():
        # Wipes every existing UI element inside the main column
        container.clear()
        with container:
            # Top section
            build_toolbar(state, refresh_all)

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

