"""Execute notebook cells in a fresh in-process IPython kernel, without sockets.

Useful in restricted environments. This checks the actual code and captures
standard notebook outputs; it does not test the Jupyter browser interface.
"""
import json
from pathlib import Path
import nbformat
from ipykernel.inprocess.manager import InProcessKernelManager

path = Path("nyc_taxi_analysis_2024.ipynb")
notebook = nbformat.read(path, as_version=4)
manager = InProcessKernelManager()
manager.start_kernel()
manager.kernel.shell.run_cell("%matplotlib inline", store_history=False)
client = manager.client()
client.start_channels()
executed = 0
try:
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        cell.outputs = []
        message_id = client.execute(cell.source)
        failed = False
        while True:
            message = client.get_iopub_msg(timeout=300)
            if message.get("parent_header", {}).get("msg_id") != message_id:
                continue
            kind = message["msg_type"]
            if kind == "execute_input":
                cell.execution_count = message["content"]["execution_count"]
            elif kind in {"stream", "display_data", "execute_result", "error"}:
                cell.outputs.append(nbformat.v4.output_from_msg(message))
                failed = failed or kind == "error"
            elif kind == "status" and message["content"]["execution_state"] == "idle":
                break
        executed += 1
        if failed:
            nbformat.write(notebook, path)
            raise RuntimeError(f"Notebook code cell {executed} failed: {cell.outputs[-1]}")
        print(f"Code cell {executed}: passed", flush=True)
finally:
    client.stop_channels()
    manager.shutdown_kernel()
nbformat.validate(notebook)
nbformat.write(notebook, path)
report = {"status": "passed", "code_cells": executed,
          "execution_method": "fresh in-process IPython kernel; standard notebook output capture",
          "limitation": "This run checks in-process execution only; separate Jupyter startup and its UI were not tested"}
Path("data/processed/notebook_validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
