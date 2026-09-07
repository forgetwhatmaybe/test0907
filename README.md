# AI 视频创作工具（节点式工作流）

节点画布式 AI 视频/图片创作工具：图片上传、香蕉生图（Gemini）、即梦、可灵、Veo、Seedance 等节点，连线编排工作流，输出节点保存结果。

## 功能

- 项目管理：新建 / 打开 / 删除 / **重命名** / 导入项目图标
- 节点画布：拖拽建节点、连线编排、自动保存（2s 防抖）
- 图片上传节点支持点击选择与拖入，自动复制到项目素材库
- 输出节点支持多批次结果、缩略图条、链式输出（输出端口可继续连下游）

## 项目结构

```
<项目目录>/
├── workflows/default.json   # 工作流（nodes + edges）
├── 素材库/                   # 上传素材
└── thumbnail.jpg            # 项目卡片缩略图
```

- 项目注册在 `~/.lanhao/config.json`（`projects` 数组 + `current_project`）
- 新建项目固定落在 `<盘符>:/AIVIDEO/<项目名>`；自定义路径需手建目录后注册 config

## 项目重命名

- 入口：项目卡片右键 →「✏ 重命名项目」
- 实现：`ProjectManager.rename_project` 目录改名，并同步更新
  - `~/.lanhao/config.json` 的项目注册与 current_project
  - `workflows/*.json` 内所有指向旧目录的绝对路径（结构化递归替换）
- 校验：空名、非法字符 `\ / : * ? " < > |`、同名目录冲突

## 踩坑记录

### 1. workflow JSON 里的路径替换必须结构化，纯文本替换永远失败

Windows 路径经 `json.dump` 写入后是 `D:\\dir\\name`（反斜杠转义）。目录改名后想把
JSON 内的旧路径批量换成新路径，用 `text.replace(str(old), str(new))` **永远匹配不上**——
因为内存字符串是单反斜杠，文件文本是双反斜杠。

正确做法：`json.loads` 后递归遍历所有字符串字段做前缀替换，再 `json.dumps` 写回：

```python
def _replace_path_prefix(value, old_str, new_str):
    if isinstance(value, str):
        return new_str + value[len(old_str):] if value.startswith(old_str) else value
    if isinstance(value, list):
        return [_replace_path_prefix(v, old_str, new_str) for v in value]
    if isinstance(value, dict):
        return {k: _replace_path_prefix(v, old_str, new_str) for k, v in value.items()}
    return value
```

### 2. 两份同名类，改错文件等于白改

历史上 `OutputNode` 同时存在于 `core/nodes/nodes.py`（真正被 import 的）和
`core/nodes/output_node.py`（无人引用的死副本）。改功能前先
`grep -rn "class Xxx" core/` 并确认 `ui/editor_window.py` 的 import 来源，
否则改了不生效。

### 3. 大文件圈复杂度门禁会拒绝编辑

`ui/editor_window.py`、`core/nodes/nodes.py` 存在大量 CC>12 的函数，编辑这些文件前
必须先把本次改动涉及的超标函数重构掉。绕行方案：把新功能写成独立模块，在入口
（main.py）以运行时注入方式挂载（参考 `core/nodes/output_upload.py`）。

### 4. styles.py 缺常量会导致节点一创建就崩

节点代码里 `styles.XXX` 引用的常量若未定义，节点实例化即 AttributeError。新增常量后
建议用正则比对全项目 `styles\.([A-Z_]+)` 引用与 `^([A-Z_]+)\s*=` 定义做静态校验。
