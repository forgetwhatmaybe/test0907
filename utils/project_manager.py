import os
import shutil
from pathlib import Path
from typing import Optional, List
import json


class ProjectManager:
    def __init__(self, config):
        self.config = config
        self.current_project_path: Optional[Path] = None
    
    def create_project(self, disk: str, project_name: str) -> Path:
        base_path = Path(f"{disk}:/AIVIDEO")
        base_path.mkdir(parents=True, exist_ok=True)
        
        project_path = base_path / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        workflow_dir = project_path / "workflows"
        workflow_dir.mkdir(exist_ok=True)
        
        self.config.add_project(str(project_path))
        self.config.set_current_project(str(project_path))
        self.current_project_path = project_path
        
        return project_path
    
    def open_project(self, project_path: str) -> bool:
        path = Path(project_path)
        if path.exists() and path.is_dir():
            self.current_project_path = path
            self.config.set_current_project(project_path)
            return True
        return False
    
    def get_project_list(self) -> List[str]:
        return self.config.get_projects()
    
    def delete_project(self, project_path: str, delete_files: bool = False):
        self.config.remove_project(project_path)
        if delete_files:
            path = Path(project_path)
            if path.exists():
                shutil.rmtree(path)
        if self.config.get_current_project() == project_path:
            self.config.set_current_project(None)
            self.current_project_path = None
    
    def import_project(self, project_path: str) -> str:
        """导入已有项目文件夹到项目列表（不移动/复制文件，仅注册）

        Args:
            project_path: 项目文件夹路径（需包含 workflows 子目录）

        Returns:
            规范化后的项目路径

        Raises:
            FileNotFoundError: 目录不存在
            ValueError: 目录缺少 workflows 子目录，不是有效项目结构
        """
        path = Path(project_path)
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"目录不存在: {path}")
        if not (path / "workflows").is_dir():
            raise ValueError("所选文件夹不是有效项目（缺少 workflows 子目录）")
        self.config.add_project(str(path))
        return str(path)

    def rename_project(self, project_path: str, new_name: str) -> str:
        """重命名项目（目录改名），并同步更新配置与工作流内的路径引用

        Args:
            project_path: 项目当前路径
            new_name: 新项目名（不含路径）

        Returns:
            新项目路径

        Raises:
            ValueError: 名称为空或含非法字符
            FileExistsError: 目标目录已存在
            FileNotFoundError: 原项目不存在
        """
        old = Path(project_path)
        if not old.exists():
            raise FileNotFoundError(f"项目不存在: {old}")

        new_name = new_name.strip()
        if not new_name:
            raise ValueError("项目名不能为空")
        invalid_chars = '\\/:*?"<>|'
        if any(ch in new_name for ch in invalid_chars):
            raise ValueError(f"项目名不能包含以下字符: {invalid_chars}")

        new = old.parent / new_name
        if new.exists():
            raise FileExistsError(f"同名目录已存在: {new}")

        old.rename(new)
        self._update_workflow_paths(old, new)

        self.config.remove_project(str(old))
        self.config.add_project(str(new))
        if self.config.get_current_project() == str(old):
            self.config.set_current_project(str(new))
        if self.current_project_path == old:
            self.current_project_path = new
        return str(new)

    @staticmethod
    def _replace_path_prefix(value, old_str: str, new_str: str):
        """递归替换 JSON 结构中所有以 old_str 开头的字符串值"""
        if isinstance(value, str):
            if value.startswith(old_str):
                return new_str + value[len(old_str):]
            return value
        if isinstance(value, list):
            return [ProjectManager._replace_path_prefix(v, old_str, new_str) for v in value]
        if isinstance(value, dict):
            return {k: ProjectManager._replace_path_prefix(v, old_str, new_str) for k, v in value.items()}
        return value

    def _update_workflow_paths(self, old: Path, new: Path):
        """把工作流 JSON 中指向旧目录的绝对路径替换为新目录

        注意：JSON 里 Windows 路径以 \\\\ 转义存储，纯文本替换无法命中，
        必须结构化解析后逐字段替换。
        """
        workflows_dir = new / "workflows"
        if not workflows_dir.exists():
            return
        old_str, new_str = str(old), str(new)
        for wf_file in workflows_dir.glob("*.json"):
            try:
                data = json.loads(wf_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"读取工作流失败 {wf_file}: {e}")
                continue
            data = self._replace_path_prefix(data, old_str, new_str)
            try:
                wf_file.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
            except Exception as e:
                print(f"更新工作流路径失败 {wf_file}: {e}")

    def get_output_path(self, node_name: str) -> Path:
        if self.current_project_path is None:
            raise ValueError("No project is currently open")
        return self.current_project_path / f"{node_name}.mp4"
    
    def save_workflow(self, workflow_data: dict, workflow_name: str = "default"):
        if self.current_project_path is None:
            raise ValueError("No project is currently open")
        
        workflow_dir = self.current_project_path / "workflows"
        workflow_file = workflow_dir / f"{workflow_name}.json"
        
        with open(workflow_file, "w", encoding="utf-8") as f:
            json.dump(workflow_data, f, indent=2, ensure_ascii=False)
        
        return workflow_file
    
    def load_workflow(self, workflow_name: str = "default") -> dict:
        if self.current_project_path is None:
            raise ValueError("No project is currently open")
        
        workflow_file = self.current_project_path / "workflows" / f"{workflow_name}.json"
        
        if workflow_file.exists():
            with open(workflow_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    
    def list_workflows(self) -> List[str]:
        if self.current_project_path is None:
            return []
        
        workflow_dir = self.current_project_path / "workflows"
        if not workflow_dir.exists():
            return []
        
        return [f.stem for f in workflow_dir.glob("*.json")]
