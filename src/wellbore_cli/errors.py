class ClientError(Exception):
    """An actionable failure with a stable machine-readable payload."""

    def __init__(self, detail, code=1, problem=None):
        super().__init__(detail)
        self.code = code
        self.problem = problem or {"title": "客户端错误", "detail": detail}
