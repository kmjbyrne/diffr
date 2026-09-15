import shutil
import subprocess

from adapters.context.review_context import context_path
from ports.ai import AIPort


class ClaudeAdapter(AIPort):
    def notify(
        self,
        review_id,
        repo_path,
        branch,
        base_branch,
        file_path,
        line_number,
        side,
        body,
    ):
        claude = shutil.which("claude")
        if not claude:
            print("[diffr] claude not found in PATH")
            return

        ctx = context_path(review_id)
        ctx_flag = []
        if ctx.exists():
            ctx_flag = ["--append-system-prompt-file", str(ctx)]

        prompt = (
            f"New review comment on `{file_path}` line {line_number} ({side}): {body}\n\n"
            f"1. Read `{file_path}` around line {line_number} for context\n"
            f"2. If comment starts with /fix, make the change and commit\n"
            f"3. Reply via: curl -s -X POST 'http://localhost:8787/api/comments/json' "
            f"-H 'Content-Type: application/json' "
            f'-d \'{{"review_id": "{review_id}", "file_path": "{file_path}", '
            f'"line_number": {line_number}, "side": "{side}", '
            f'"body": "<reply>", "author": "claude"}}\''
        )

        cmd = [
            claude,
            "--bg",
            "--allow-dangerously-skip-permissions",
            "--dangerously-skip-permissions",
            *ctx_flag,
            prompt,
        ]
        print(f"[diffr] spawning: {' '.join(cmd[:4])}... (cwd={repo_path})")
        try:
            proc = subprocess.Popen(
                cmd, cwd=repo_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            print(f"[diffr] spawned pid={proc.pid}")
        except OSError as e:
            print(f"[diffr] spawn failed: {e}")
