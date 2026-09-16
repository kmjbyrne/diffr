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

        self._spawn(claude, prompt, ctx_flag, repo_path)

    def review_code(
        self,
        review_id,
        repo_path,
        branch,
        base_branch,
        files,
    ):
        claude = shutil.which("claude")
        if not claude:
            print("[diffr] claude not found in PATH")
            return

        ctx = context_path(review_id)
        ctx_flag = []
        if ctx.exists():
            ctx_flag = ["--append-system-prompt-file", str(ctx)]

        file_list = "\n".join(
            f"- `{f['path']}` ({f.get('status', 'modified')})" for f in files
        )

        prompt = (
            f"Review the code changes on branch `{branch}` compared to `{base_branch}`.\n\n"
            f"Changed files:\n{file_list}\n\n"
            f"For each file, read it and review the diff. Look for:\n"
            f"- Bugs, logic errors, off-by-one mistakes\n"
            f"- Security issues\n"
            f"- Performance problems\n"
            f"- Code that is hard to understand or maintain\n"
            f"- Missing error handling at system boundaries\n\n"
            f"For each finding, post a comment on the specific line using:\n"
            f"curl -s -X POST 'http://localhost:8787/api/comments/json' "
            f"-H 'Content-Type: application/json' "
            f'-d \'{{"review_id": "{review_id}", "file_path": "<file>", '
            f'"line_number": <line>, "side": "right", '
            f'"body": "<your review comment>", "author": "claude"}}\'\n\n'
            f"Post each comment individually as you find issues. "
            f"Be specific and reference the actual code. "
            f"Skip files that look fine. Do not post a comment if there is nothing wrong."
        )

        self._spawn(claude, prompt, ctx_flag, repo_path)

    def _spawn(self, claude, prompt, ctx_flag, repo_path):
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
