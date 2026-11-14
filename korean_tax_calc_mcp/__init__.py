"""한국 세금 계산 MCP 서버."""
from importlib.metadata import PackageNotFoundError, version as _version

try:  # 설치된 패키지 버전(pyproject)을 그대로 쓴다
    __version__ = _version("korean-tax-calc-mcp")
except PackageNotFoundError:
    __version__ = ""
