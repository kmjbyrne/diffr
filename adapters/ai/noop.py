from ports.ai import AIPort


class NoOpAI(AIPort):
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
        pass

    def review_code(
        self,
        review_id,
        repo_path,
        branch,
        base_branch,
        files,
    ):
        pass
