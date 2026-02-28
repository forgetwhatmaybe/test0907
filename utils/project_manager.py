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
