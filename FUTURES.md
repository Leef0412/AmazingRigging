# FUTURES.md - 知识沉淀

## 功能修复记录

### IK/FK Settings 删除 bone 后 UI 不同步

**日期**: 2026-04-24
**状态**: 已完成

#### 问题描述
配置的 IK/FK/IK Ctrl bone 被删除后，UI 选项仍停留在已失效的 bone 上，用户无法察觉配置已失效。

#### 根因分析
1. `sync_set_bone_ui` 只检查 **config data**（持久化的 custom property）
2. 但用户配置后，值存在 **UI PropertyGroup**（`amazing_set_bone_ui.ik.armature/.bone`），没有持久化到 config data
3. `sync_set_bone_ui` case 4 当 config data 为空时，**直接保留 UI 原样**，没有检查 UI PropertyGroup 的值是否仍有效

#### 修复方案
**文件**: `utils_set_bone_config.py`

在 `sync_set_bone_ui` 的 case 4 中增加检查 UI PropertyGroup：

```python
else:
    # 情况4：没有持久化配置数据
    # 但 UI PropertyGroup 里可能有值，需要检查是否仍有效
    ui_armature = ui_target.armature
    ui_bone = ui_target.bone
    if ui_armature and ui_bone:
        # 检查 UI PropertyGroup 里的 bone 是否还存在
        bone_exists = ui_bone in ui_armature.data.bones if ui_armature.data else False
        if not bone_exists:
            # bone 已被删除，清空 UI
            ui_target.armature = None
            ui_target.bone = ""
```

#### 验证结果
- Blender MCP 真机测试通过
- IK bone 被删除后，UI 正确清空（armature=None, bone=''）
- FK/IK_CTRL 保持不变（因为那些 bone 仍存在）

#### 相关文件
- `utils_set_bone_config.py` - sync_set_bone_ui 函数
- `__init__.py` - check_bone_changes 函数
