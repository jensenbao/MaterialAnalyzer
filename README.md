# MaterialAnalyzer 插件说明

MaterialAnalyzer 是一个面向 UE 材质分析流程的插件提交包。它负责从 UE 侧提取材质图结构与基础属性，通过 Python 和 Web 分析流程生成结果，并在分析完成后把规则沉淀为可复用的正式 Skill 模块。

## 1. 安装与首次使用

首次接入建议按下面顺序执行：

1. 关闭 Unreal Editor。
2. 将本目录复制到目标 UE 项目：`<YourUEProject>/Plugins/MaterialAnalyzer`
3. 在插件目录执行 `setup_python_env.ps1`，让脚本自动定位 UE 自带 Python、创建 `.venv` 并安装依赖。
4. 右键 `.uproject`，执行 Generate Visual Studio project files。
5. 用 Visual Studio 打开工程并编译 `Development Editor`。
6. 启动 UE，确认插件已启用。

PowerShell：
`./setup_python_env.ps1`

CMD：
`setup_python_env.bat`

脚本行为：
1. 自动定位 UE 内置 Python。
2. 在 `Plugins/MaterialAnalyzer/Content/Python/.venv` 创建虚拟环境。
3. 安装 `requirements_streamlit.txt` 中的依赖并做导入校验。
4. 完成后再次打开 UE，启动阶段只检查环境，不再安装依赖。

## 2. Python 与 Web 侧脚本

核心脚本统一维护在插件目录：

1. `Plugins/MaterialAnalyzer/Content/Python/ue_http_bridge_server.py`
2. `Plugins/MaterialAnalyzer/Content/Python/ue_open_web_for_selected_material.py`
3. `Plugins/MaterialAnalyzer/Content/Python/material_analyzer_streamlit_app.py`
4. `Plugins/MaterialAnalyzer/Content/Python/material_analyzer_init.py`
5. `Plugins/MaterialAnalyzer/Content/Python/init_unreal.py`

说明：
1. 日常维护以插件目录版本为准，便于跨项目复用与分发。
2. 插件不在 UE 启动时自动安装依赖，避免首次启动卡住编辑器。
3. `init_unreal.py` 会作为插件启动入口，执行 Python 侧初始化逻辑。

## 3. Skill 模块导出

分析完成后，插件会把正式 Skill 模块导出到：

1. `MaterialAnalyzer/Skills/*.py`

每个 Skill 模块包含：
1. `skill_id`、`skill_name`、`version` 等模块元数据。
2. 当前材质路径与适用范围 `applies_to`。
3. 统一结构化的 `rules` 列表。

职责边界：
1. C++ 插件负责 UE API 取数和桥接。
2. Python / Web 负责展示分析结果和触发 AI。
3. Skill 以正式模块脚本形式沉淀，作为后续规则库基础。

## 4. 导出提交包

在插件目录执行：

1. PowerShell
`./export_submission.ps1`

默认输出：
1. 输出到插件目录下的相对路径 `Submission/MaterialAnalyzer`
2. 如需指定位置，可执行 `./export_submission.ps1 -OutputRoot '<YourOutputRoot>'`

导出包包含：
1. `MaterialAnalyzer.uplugin`
2. `Source/`
3. `Content/`
4. `Skills/`
5. `setup_python_env.ps1`
6. `setup_python_env.bat`
7. `README.md`

导出包不包含：
1. 宿主工程内容。
2. 插件 `Binaries/`。
3. 插件 `Intermediate/`。
4. Python 虚拟环境 `.venv/`。
5. 本地 `.streamlit/` 和 `__pycache__/`。

## 5. 已提供的 C++ 接口

类名：`UMaterialAnalyzerBPLibrary`

函数：
1. `GetMaterialSummaryJson(material_path)`
2. `GetSelectedMaterialSummaryJson()`
3. `GetMaterialPropertiesJson(material_path)`
4. `GetMaterialShaderCodeJson(material_path)`
5. `CompileMaterialJson(material_path)`

其中后两项当前仍为占位接口。

## 6. 在 UE Python 中测试

先选中一个材质后执行：

`py import unreal; print(unreal.MaterialAnalyzerBPLibrary.get_selected_material_summary_json())`

按路径测试：

`py import unreal; print(unreal.MaterialAnalyzerBPLibrary.get_material_summary_json('/Game/Path/To/YourMaterial.YourMaterial'))`

仅材质属性测试：

`py import unreal; print(unreal.MaterialAnalyzerBPLibrary.get_material_properties_json('/Game/Path/To/YourMaterial.YourMaterial'))`

## 7. 当前实现范围

已实现：
1. 导出基础材质信息，例如路径、名称、Domain、BlendMode、TwoSided。
2. 导出节点列表，基于 MaterialEditingLibrary。
3. 导出边关系，通过表达式输入反射构建。
4. 导出常见输出绑定，例如 BaseColor、Emissive、Opacity、Normal、Roughness、Metallic。

暂未实现：
1. Shader 代码导出。
2. 强制编译并返回编译日志。
3. 注释框、分组、孤立节点的精确标注。

## 8. 常见问题

1. Python 找不到 `MaterialAnalyzerBPLibrary`
原因：插件未编译成功或未启用。

2. 返回 `asset_not_found`
原因：路径必须是完整对象路径，例如 `/Game/.../M_Name.M_Name`。

3. 返回节点数为 0
原因：材质表达式可能主要位于函数或实例链中，后续需要补函数展开与实例追溯。