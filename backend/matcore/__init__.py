"""MatNexus 계산 커널.

DB도 HTTP도 모르는 순수 계산만 여기 산다. 입력과 출력은 dataclass다.
경계는 tests/architecture/test_boundaries.py 가 검사한다.
"""

from matcore.registry import ParamSpec, Plugin, get, list_plugins, register

__all__ = ["ParamSpec", "Plugin", "get", "list_plugins", "register"]
