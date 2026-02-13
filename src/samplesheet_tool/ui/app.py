# app.py
# control UI state/view
# 

from pathlib import Path
from nicegui import ui

from samplesheet_tool.ui.state import RunState, load_index_preset, default_store_dir
from samplesheet_tool.ui.views import build_main_view
from samplesheet_tool.ui.runtime_config import load_runtime_config


def main() -> None:
    # get default data storing directory
    base = default_store_dir()

    # load runtime config and apply to state
    cfg = load_runtime_config(base)

    # create state (mkdir plans/temp/outputs via __post_init__)
    state = RunState(base_dir=base)

    # apply config to state
    state.apply_runtime_config(cfg)
    
    # load index preset once at startup
    load_index_preset(state)

    # render UI
    build_main_view(state)
    ui.run(title="SampleSheet Tool UI", reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()

