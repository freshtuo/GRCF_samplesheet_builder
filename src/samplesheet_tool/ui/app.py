# app.py
# control UI state/view
# 

from nicegui import ui
from samplesheet_tool.ui.state import RunState
from samplesheet_tool.ui.views import build_main_view


def main() -> None:
    state = RunState()
    build_main_view(state)
    ui.run(title="SampleSheet Tool UI", reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()

