
import sys
import os
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path.cwd() / "src"))

from exames_pipeline.mcp_server import _merge_review_meta, _run, _workspace_path, WorkspaceStage

workspace = "EX-MatA635-EE-2022"
ws_dir = _workspace_path(workspace)

print(f"Merging review + meta for {workspace}...")
err = _merge_review_meta(workspace)
if err:
    print(err)
    sys.exit(1)

raw_path = ws_dir / "questoes_raw.json"
print(f"Running micro-lint on {raw_path}...")
lint_result = _run(["micro-lint", str(raw_path)])
print(lint_result["stdout"])
if not lint_result["ok"]:
    print("Micro-lint failed")
    sys.exit(1)

print(f"Running validate on {raw_path}...")
val_result = _run(["validate", str(raw_path)])
print(val_result["stdout"])
if val_result["ok"]:
    ws = WorkspaceStage(ws_dir)
    ws.transition("validated")
    print("Workspace transitioned to 'validated'")
else:
    print("Validation failed")
    sys.exit(1)
