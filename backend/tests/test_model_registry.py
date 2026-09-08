"""模型注册表的回归测试。

必须在**独立子进程**里跑：pytest 的 conftest 会把所有模型都导进来，
在主进程里断言等于没测——这正是当初 worker 崩了而单元测试全绿的原因。
"""

import subprocess
import sys

EXPECTED_TABLES = {
    "proposals",
    "controls",
    "control_sources",
    "control_relations",
    "users",
    "audit_log",
    "llm_provider_config",
    "llm_task_routing",
    "llm_call",
    "llm_redaction_rule",
    "app_setting",
    "documents",
    "clauses",
    "clause_chunks",
    "query_expansion_cache",
}


def _tables_after_importing(module: str) -> set[str]:
    code = (
        f"import {module}\n"
        "from app.db import Base\n"
        "print(','.join(sorted(Base.metadata.tables)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    return set(result.stdout.strip().split(","))


def test_worker_entrypoint_registers_every_model():
    """worker 只 import 自己的任务模块时，users 表不在 metadata 里，
    documents.uploaded_by 这个跨模块外键就解析不了——**每一份文档的解析
    都会在 flush 时失败**，而单元测试完全看不出来。
    """
    assert EXPECTED_TABLES <= _tables_after_importing("app.worker")


def test_api_entrypoint_registers_every_model():
    assert EXPECTED_TABLES <= _tables_after_importing("app.main")


def test_registry_alone_is_enough():
    """入口应当依赖 app.models，而不是依赖"碰巧 import 了哪个路由"。"""
    assert EXPECTED_TABLES <= _tables_after_importing("app.models")


def test_cross_module_foreign_keys_resolve():
    """列级外键是惰性解析的：configure_mappers() 不报错，要到 flush
    排表依赖顺序时才炸。所以必须显式验证外键真的能解析。
    """
    code = (
        "import app.worker\n"
        "from app.db import Base\n"
        "from sqlalchemy import Table\n"
        "for fk in Base.metadata.tables['documents'].foreign_keys:\n"
        "    fk.column\n"       # 触发解析，解析不了会抛 NoReferencedTableError
        "for fk in Base.metadata.tables['clause_chunks'].foreign_keys:\n"
        "    fk.column\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-400:]
    assert "ok" in result.stdout
