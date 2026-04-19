
import os
import sys
from pathlib import Path

# Add src to sys.path
repo_root = Path("/Users/adrianoushinohama/Desktop/Exames Nacionais")
sys.path.append(str(repo_root / "src"))

# Mock the environment
os.environ["PIPELINE_ROOT"] = str(repo_root)

from exames_pipeline.mcp_server import workspace_status, list_workspaces, run_stage, get_cc_context

if len(sys.argv) > 1:
    cmd = sys.argv[1]
    if cmd == "status":
        print(workspace_status(sys.argv[2]))
    elif cmd == "list":
        print(list_workspaces())
    elif cmd == "context":
        # context workspace_cc id_item
        print(get_cc_context(sys.argv[2], sys.argv[3]))
    elif cmd == "run":
        # run workspace stage [pdf_path] [workspace_cc] [pdf_cc_path]
        ws = sys.argv[2]
        stage = sys.argv[3]
        pdf = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "None" else None
        ws_cc = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "None" else None
        pdf_cc = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] != "None" else None
        print(run_stage(ws, stage, pdf_path=pdf, workspace_cc=ws_cc, pdf_cc_path=pdf_cc))
else:
    print(list_workspaces())
