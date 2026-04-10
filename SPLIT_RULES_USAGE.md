# Split Bones Rules 功能使用说明

## 功能概述
Split Bones Rules 允许用户自定义骨骼拆分规则，通过 Prefix（前缀）和 Exact Match（精确匹配）来分类 bone collections。

## 位置
- **Data 面板**: 在 Blender 右侧 Properties 面板中，点击 Data 标签（骨骼图标）
- **Split Bones Rules**: 位于面板顶部，独立的新面板
- **Ctrl bones UI - Amazing Rigging**: 位于下方，用于编辑 grid data

## 默认规则
打开面板时会自动创建2个默认规则：

### 1. Ctrl Bones
- **Prefix**: `DEF-`
- **Exact Match**: `Root`
- 匹配所有以 `DEF-` 开头或名为 `Root` 的骨骼

### 2. Other (Deform Bones)
- **空规则**（无 Prefix 和 Exact Match）
- 自动匹配所有未被其他规则匹配的 bone collections

## 使用方法

### 重命名规则
1. 点击规则名称右侧的铅笔图标
2. 规则名称变为可编辑状态
3. 输入新名称
4. 按 Enter 确认，Esc 取消

### 初始化 Amazing Rigging UI
1. 配置好 Split Rules 后
2. 点击面板底部的 **"Init Amazing Rigging UI"** 按钮
3. 系统会根据 Split Rules 自动拆分 bone collections 并生成 UI

## 使用方法

### 添加新规则
1. 点击底部的 `+ Add Split Rule` 按钮
2. 新规则会添加到列表末尾
3. 点击规则名称展开/折叠

### 编辑规则名称
- 目前规则名称暂时固定，后续可添加编辑功能

### 添加 Prefix
1. 展开规则
2. 点击 `+ Add Prefix` 按钮
3. 点击铅笔图标进入编辑模式
4. 输入前缀（如 `CTRL-`, `MDEF-` 等）
5. 按 Enter 确认，Esc 取消

### 添加 Exact Match
1. 展开规则
2. 点击 `+ Add Exact Match` 按钮
3. 点击铅笔图标进入编辑模式
4. 输入完整骨骼名称（如 `MASTER`, `COG` 等）
5. 按 Enter 确认，Esc 取消

### 删除 Prefix/Exact Match
- 点击对应行右侧的 `X` 按钮

### 规则排序
- 使用规则标题栏右侧的 `↑` `↓` 按钮上下移动规则

### 删除规则
- 点击规则标题栏右侧的 `X` 按钮
- **注意**: 至少保留1个规则

## Sidebar 显示
在 3D Viewport 的 Sidebar (N键) > Amazing Rigging 面板中：
- 会根据 Split Rules 自动分类显示 bone collections
- 每个规则显示为一行，包含匹配的所有 collections
- 可以点击 toggle 按钮显示/隐藏对应的 collections

## 示例配置

### 配置1: 基础设置
```
Rule 1: Ctrl Bones
  - Prefix: DEF-
  - Exact: Root

Rule 2: Other
  - (empty)
```

### 配置2: 多前缀设置
```
Rule 1: Main Controls
  - Prefix: CTRL-
  - Prefix: MCTRL-
  - Exact: Root
  - Exact: COG

Rule 2: Deform Bones
  - Prefix: DEF-
  - Prefix: MDEF-

Rule 3: Other
  - (empty)
```

## 注意事项
1. 规则按顺序匹配，第一个匹配的规则会"捕获"对应的 collections
2. "Other" 规则（空规则）会捕获所有未被匹配到的 collections
3. 修改规则后，Sidebar 会自动更新显示
4. 至少需要保留1个规则
