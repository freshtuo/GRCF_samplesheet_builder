# app.py
# control UI state/view
# 

from nicegui import ui

from samplesheet_tool.ui.shared_catalog import load_shared_catalog
from samplesheet_tool.ui.state import RunState, default_store_dir
from samplesheet_tool.ui.views import build_main_view
from samplesheet_tool.ui.runtime_config import load_runtime_config


def main() -> None:
    """Initialize app state, load shared data, and start the NiceGUI UI."""
    # get default data storing directory
    base = default_store_dir()

    # load runtime config and apply to state
    cfg = load_runtime_config(base)

    # create state (mkdir plans/temp/outputs via __post_init__)
    state = RunState(base_dir=base)

    # apply config to state
    state.apply_runtime_config(cfg)

    # load shared catalog if configured
    if state.shared_catalog_dir is not None:
        try:
            state.catalog = load_shared_catalog(state.shared_catalog_dir)
            state.ensure_valid_project_selection()
        except PermissionError as e:
            state.startup_warning = (
                f"No permission to read the shared catalog folder: {e}. "
                'The app is still usable, but shared projects and index tables may be unavailable. '
                'Use "Refresh Shared" in the toolbar after access is restored.'
            )
        except Exception as e:
            state.startup_warning = (
                f"Shared catalog load failed: {e}. "
                'The app is still usable, but shared projects and index tables may be unavailable. '
                'Use "Refresh Shared" in the toolbar to try again.'
            )

    # render UI
    build_main_view(state)
    ui.run(title="SampleSheet Tool UI", reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
