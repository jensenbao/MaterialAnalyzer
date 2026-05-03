# MaterialAnalyzer 插件说明

MaterialAnalyzer 是一个面向 Unreal Editor 的材质分析插件。它负责从 UE 侧提取材质图结构与基础属性，通过本地 Python / Web 分析流程展示结果，并在分析完成后把规则沉淀为可复用的 Skill 模块。

当前建议支持范围：
1. 当前版本仅按 Unreal Engine 5.6 环境开发与验证。
2. 当前环境脚本仅按 Windows 设备编写与验证。
3. 其他 UE 版本暂不做兼容保证。

## 0. 安装前提

在其他设备接入本插件前，请先确认下面几项：

1. 目标机器是 Windows。
2. 已安装 Unreal Engine 5.6，且安装版或源码版引擎中包含 `Engine/Binaries/ThirdParty/Python3/Win64/python.exe`。
3. 宿主项目具备 C++ 编译能力；如果是纯蓝图项目，需要先转成可编译工程。
4. 目标机器可以正常创建 Python 虚拟环境，并能通过 pip 下载依赖。
5. Unreal Editor 侧需要启用 Python 相关能力；如果目标环境关闭了 PythonScriptPlugin，插件的 Web / Python 工作流将无法正常启动。
6. 首次执行环境安装时，建议目标机器可以访问外网 Python 包源。

补充说明：
1. 本插件是 Editor-only 工具插件，不是运行时游戏插件。
2. 当前提交包附带的是源码插件，不包含可直接复用的预编译二进制。

## 1. 安装与首次使用

首次接入前先确认目标项目类型，再按对应流程处理。

### C++ 项目

1. 确保在复制插件、生成工程文件、编译或执行环境脚本时，Unreal Editor 处于关闭状态。
2. 将本目录复制到目标 UE 项目：`<YourUEProject>/Plugins/MaterialAnalyzer`
3. 右键 `.uproject`，执行 Generate Visual Studio project files。
4. 用 Visual Studio 打开工程并编译 `Development Editor`，先完成 C++ 插件编译。
5. 确认插件已能随工程正常加载后，关闭 Unreal Editor。
6. 在插件目录执行 `setup_python_env.ps1`，让脚本自动定位 UE 自带 Python、创建 `.venv` 并安装依赖。
7. 再次启动 UE，确认插件和 Python 侧功能均已启用。

### 蓝图项目

当前提交包默认提供的是源码插件，不附带项目侧可直接复用的预编译产物。纯蓝图项目需要先具备 C++ 编译能力，再编译插件。

1. 如果项目还是纯蓝图项目，先不要复制本插件，先打开原项目并添加一个空的 C++ 类，把项目转换为可编译工程。
2. 等 UE 为项目生成 C++ 工程骨架后，关闭 Unreal Editor。
3. 将本目录复制到目标 UE 项目：`<YourUEProject>/Plugins/MaterialAnalyzer`
4. 右键 `.uproject`，执行 Generate Visual Studio project files。
5. 用 Visual Studio 打开工程并编译 `Development Editor`，先完成宿主工程和插件的首次编译。
6. 编译通过并确认插件可正常加载后，关闭 Unreal Editor。
7. 在插件目录执行 `setup_python_env.ps1`，让脚本自动定位 UE 自带 Python、创建 `.venv` 并安装依赖。
8. 再次启动 UE，确认插件和 Python 侧功能均已启用。

无论是哪种项目，都建议在插件编译完成后，再执行下面的环境配置命令。

PowerShell：
`./setup_python_env.ps1`

CMD：
`setup_python_env.bat`

推荐顺序：
1. 先完成宿主工程和插件编译。
2. 关闭 Unreal Editor。
3. 再运行 `setup_python_env.ps1` 或 `setup_python_env.bat`。
4. 环境安装完成后重新打开 UE。

脚本行为：
1. 自动检查当前项目对应的 Unreal Editor 是否正在运行；如果正在运行，则拒绝继续，避免虚拟环境和进程占用冲突。
2. 自动定位 UE 内置 Python；优先使用显式传入的 `-EngineRoot`，其次尝试项目 EngineAssociation、注册表、环境变量和常见安装目录扫描。
3. 在 `Plugins/MaterialAnalyzer/Content/Python/.venv` 创建或重建虚拟环境。
4. 安装 `requirements_streamlit.txt` 中的依赖并做导入校验。
5. 完成后再次打开 UE；插件启动阶段只检查环境与 bridge，不再在启动时安装依赖。

脚本入口说明：
1. `setup_python_env.ps1` 是主入口，包含完整逻辑。
2. `setup_python_env.bat` 只是对 `setup_python_env.ps1` 的一层 CMD 包装，便于在没有直接使用 PowerShell 的情况下调用。

可选参数：
1. 当脚本无法自动识别引擎位置时，可执行：`./setup_python_env.ps1 -EngineRoot '<UE_ROOT_PATH>'`

其他设备可复用性说明：
1. 这两个脚本可以直接随插件一起复制到其他 Windows 设备使用。
2. 前提是目标设备满足本 README 第 0 节中的环境条件。
3. 如果目标机器没有外网或 pip 源不可用，脚本本身仍然能执行，但依赖安装会失败。
4. 如果目标机器上的 UE 安装位置未写入注册表，也不在脚本扫描范围内，请用 `-EngineRoot` 显式指定。

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
4. 当前进入 UE 后不会再弹出“是否打开 Web”对话框；如需打开 Web，请在编辑器菜单中使用 `Window > Material Analyzer`。

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

4. `setup_python_env.ps1` 提示找不到 Unreal Engine python.exe
原因：目标机器上的 UE 安装路径未被脚本自动识别。
处理：使用 `-EngineRoot` 参数显式传入引擎根目录。

5. 环境脚本在其他设备执行失败
原因通常是以下几类之一：
1. Unreal Editor 没有关闭。
2. 目标机器没有可用的 UE 内置 Python。
3. pip 无法访问依赖源。
4. 目标项目本身还没有 C++ 编译能力。

6. 菜单里能看到 `Window > Material Analyzer`，但打开后 Web 没起来
原因：本地 bridge 或 Streamlit 依赖未完成安装，或目标机器上的 Python / 网络环境异常。
处理：先重新执行 `setup_python_env.ps1`，再重启 UE。
