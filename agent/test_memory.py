"""agent/test_memory.py"""
import pytest
import tempfile
import os
import json
from agent.memory import ProjectMemory


class TestProjectMemory:
    def test_create_default_memory(self):
        """测试创建默认记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ProjectMemory(tmpdir)
            assert memory.data["project_path"] == tmpdir
            assert "structure" in memory.data
            assert "tools" in memory.data
            assert "updated_at" in memory.data

    def test_load_existing_memory(self):
        """测试加载已存在的记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建已有记忆
            memory_file = os.path.join(tmpdir, ".agent-memory.json")
            existing_data = {
                "project_path": tmpdir,
                "updated_at": "2026-04-07T10:00:00",
                "structure": {"src_dir": "src"},
                "tools": {"test_command": "pytest"},
                "notes": []
            }
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f)

            # 加载
            memory = ProjectMemory(tmpdir)
            assert memory.data["structure"]["src_dir"] == "src"
            assert memory.data["tools"]["test_command"] == "pytest"

    def test_save_memory(self):
        """测试保存记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ProjectMemory(tmpdir)
            memory.update_structure({"src_dir": "lib"})
            memory.save()

            # 验证文件存在
            memory_file = os.path.join(tmpdir, ".agent-memory.json")
            assert os.path.exists(memory_file)

            # 验证内容
            with open(memory_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                assert saved["structure"]["src_dir"] == "lib"

    def test_update_structure(self):
        """测试更新项目结构"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ProjectMemory(tmpdir)
            memory.update_structure({"src_dir": "source", "test_dir": "tests"})
            assert memory.data["structure"]["src_dir"] == "source"
            assert memory.data["structure"]["test_dir"] == "tests"

    def test_update_tools(self):
        """测试更新工具配置"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ProjectMemory(tmpdir)
            memory.update_tools({"test_command": "python -m pytest"})
            assert memory.data["tools"]["test_command"] == "python -m pytest"

    def test_get_context(self):
        """测试获取注入字符串"""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = ProjectMemory(tmpdir)
            memory.update_structure({"src_dir": "src", "test_dir": "tests"})
            memory.update_tools({"test_command": "pytest"})

            context = memory.get_context()
            assert "## 项目记忆" in context
            assert "src" in context
            assert "tests" in context
            assert "pytest" in context
