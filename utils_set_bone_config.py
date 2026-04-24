"""
SET-骨骼 IK/FK/IK CTRL 配置数据持久化模块

提供保存/加载/验证/清理 SET-骨骼配置数据的功能。
配置数据存储在 PoseBone 的自定义属性中，使用 JSON 格式。
"""

import bpy
import json
from . import utils_bone_data


# 配置类型常量
CONFIG_IK = "ik"
CONFIG_FK = "fk"
CONFIG_IK_CTRL = "ik_ctrl"

# 配置版本
CONFIG_VERSION = 1


def _get_config_key(config_type):
    """根据配置类型获取对应的自定义属性键"""
    if config_type == CONFIG_IK:
        return utils_bone_data.KEY_IK_CONFIG
    elif config_type == CONFIG_FK:
        return utils_bone_data.KEY_FK_CONFIG
    elif config_type == CONFIG_IK_CTRL:
        return utils_bone_data.KEY_IK_CTRL_CONFIG
    return None


def save_set_bone_config(pose_bone, config_type, armature_obj, bone_name):
    """
    保存 SET-骨骼的配置到自定义属性
    
    Args:
        pose_bone: PoseBone 对象
        config_type: 配置类型 ("ik", "fk", "ik_ctrl")
        armature_obj: 目标 armature 对象 (None 时清除配置)
        bone_name: 目标骨骼名称
    
    Returns:
        bool: 保存是否成功
    """
    if not pose_bone:
        return False
    
    config_key = _get_config_key(config_type)
    if not config_key:
        return False
    
    # 如果 armature_obj 为 None，清除配置
    if not armature_obj:
        if config_key in pose_bone:
            del pose_bone[config_key]
        return True
    
    # 确保 armature 有 UUID
    armature_uuid = utils_bone_data.get_or_create_armature_uuid(armature_obj.data)
    
    # 构建配置数据
    config_data = {
        "version": CONFIG_VERSION,
        "armature_name": armature_obj.data.name,
        "armature_uuid": armature_uuid,
        "bone_name": bone_name or ""
    }
    
    # 序列化为 JSON 并保存
    try:
        pose_bone[config_key] = json.dumps(config_data, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] 保存 SET-骨骼配置失败: {e}")
        return False


def load_set_bone_config(pose_bone, config_type):
    """
    从自定义属性加载 SET-骨骼配置
    
    Args:
        pose_bone: PoseBone 对象
        config_type: 配置类型 ("ik", "fk", "ik_ctrl")
    
    Returns:
        dict: {
            "armature_obj": Object 或 None,
            "bone_name": str,
            "valid": bool,
            "config_data": dict 或 None
        }
    """
    result = {
        "armature_obj": None,
        "bone_name": "",
        "valid": False,
        "config_data": None
    }
    
    if not pose_bone:
        return result
    
    config_key = _get_config_key(config_type)
    if not config_key:
        return result
    
    # 读取配置数据
    config_str = pose_bone.get(config_key, "")
    if not config_str:
        return result
    
    # 解析 JSON
    try:
        config_data = json.loads(config_str)
        result["config_data"] = config_data
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[ERROR] 解析 SET-骨骼配置失败: {e}")
        # 配置数据损坏，清理
        if config_key in pose_bone:
            del pose_bone[config_key]
        return result
    
    # 验证版本号
    version = config_data.get("version", 0)
    if version != CONFIG_VERSION:
        print(f"[WARNING] SET-骨骼配置版本不匹配: {version} (期望 {CONFIG_VERSION})")
        # 可以尝试迁移，但当前版本直接返回无效
        return result
    
    # 通过 UUID 查找 armature
    armature_uuid = config_data.get("armature_uuid", "")
    armature_name = config_data.get("armature_name", "")
    bone_name = config_data.get("bone_name", "")
    
    result["bone_name"] = bone_name
    
    # 优先通过 UUID 查找
    armature_obj = utils_bone_data.find_armature_obj_by_uuid(armature_uuid)
    
    # 如果 UUID 查找失败，尝试通过名称查找
    if not armature_obj and armature_name:
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE' and obj.data.name == armature_name:
                armature_obj = obj
                # 找到后更新 UUID
                if hasattr(armature_obj.data, 'uuid') and not armature_obj.data.uuid:
                    armature_obj.data.uuid = armature_uuid
                break
    
    result["armature_obj"] = armature_obj
    
    # 验证配置有效性
    if armature_obj and bone_name:
        # 检查骨骼是否存在 - 使用 OR 逻辑，因为骨骼删除后到 depsgraph 更新前，
        # arm_data.bones 和 pose.bones 可能暂时不同步
        bone_in_armdata = armature_obj.data.bones.get(bone_name)
        configured_pb = armature_obj.pose.bones.get(bone_name)
        if configured_pb is not None or bone_in_armdata is not None:
            result["valid"] = True
        else:
            result["valid"] = False
    elif armature_obj and not bone_name:
        # 只有 armature 没有 bone，视为部分有效
        result["valid"] = False
    else:
        result["valid"] = False

    return result


def clear_set_bone_config(pose_bone, config_type=None):
    """
    清除 SET-骨骼的配置
    
    Args:
        pose_bone: PoseBone 对象
        config_type: 配置类型 (None 时清除所有三种配置)
    
    Returns:
        bool: 清除是否成功
    """
    if not pose_bone:
        return False
    
    if config_type is not None:
        # 清除指定类型的配置
        config_key = _get_config_key(config_type)
        if config_key and config_key in pose_bone:
            del pose_bone[config_key]
    else:
        # 清除所有三种配置
        for cfg_type in [CONFIG_IK, CONFIG_FK, CONFIG_IK_CTRL]:
            config_key = _get_config_key(cfg_type)
            if config_key and config_key in pose_bone:
                del pose_bone[config_key]
    
    return True


def cleanup_invalid_configs():
    """
    遍历所有 armature 的所有 SET-骨骼，清除无效的配置引用

    应该在以下时机调用:
    - 场景加载后
    - 检测到 armature 或 bone 被删除后
    - undo 操作后
    """
    cleaned_count = 0

    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE':
            continue

        for pose_bone in obj.pose.bones:
            # 只处理 SET- 前缀的骨骼
            if not pose_bone.name.startswith("SET-"):
                continue

            for config_type in [CONFIG_IK, CONFIG_FK, CONFIG_IK_CTRL]:
                result = load_set_bone_config(pose_bone, config_type)

                # 当 config_data 存在但 valid 为 False 时，说明配置的 bone 已失效
                # 此时无论 armature 是否存在，都应该清除配置
                if result["config_data"] is not None and not result["valid"]:
                    if result["bone_name"]:
                        # bone 被删除（armature 可能存在也可能不存在），清除配置
                        clear_set_bone_config(pose_bone, config_type)
                        cleaned_count += 1
                        print(f"[DEBUG] cleanup_invalid_configs: cleared {config_type} config for {pose_bone.name} (bone '{result['bone_name']}' deleted)")
                    # 如果 bone_name 为空（用户从未配置），不处理

    if cleaned_count > 0:
        print(f"[INFO] 清理了 {cleaned_count} 个无效的 SET-骨骼配置")

    return cleaned_count


def refresh_all_configs():
    """
    刷新所有 SET-骨骼配置，确保 UUID 已初始化
    
    应该在文件加载后调用，确保所有 armature 的 UUID 已初始化
    """
    refreshed_count = 0
    
    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE':
            continue
        
        # 确保 armature 有 UUID
        if hasattr(obj.data, 'uuid') and not obj.data.uuid:
            utils_bone_data.get_or_create_armature_uuid(obj.data)
        
        for pose_bone in obj.pose.bones:
            if not pose_bone.name.startswith("SET-"):
                continue
            
            for config_type in [CONFIG_IK, CONFIG_FK, CONFIG_IK_CTRL]:
                config_key = _get_config_key(config_type)
                if not config_key or config_key not in pose_bone:
                    continue
                
                # 读取配置
                try:
                    import json
                    config_data = json.loads(pose_bone[config_key])
                    
                    # 通过 armature_name 重新获取 UUID
                    armature_name = config_data.get("armature_name", "")
                    if armature_name:
                        arm_data = bpy.data.armatures.get(armature_name)
                        if arm_data:
                            # 找到 armature，更新 UUID
                            current_uuid = getattr(arm_data, 'uuid', '')
                            if current_uuid:
                                config_data["armature_uuid"] = current_uuid
                                pose_bone[config_key] = json.dumps(config_data, ensure_ascii=False)
                                refreshed_count += 1
                except Exception as e:
                    print(f"[ERROR] 刷新配置失败: {e}")
    
    if refreshed_count > 0:
        print(f"[INFO] 刷新了 {refreshed_count} 个 SET-骨骼配置的 UUID")
    
    return refreshed_count


def sync_set_bone_ui(context, pose_bone):
    """
    同步 SET-骨骼的配置到 UI

    当用户选中 SET-骨骼时调用，将持久化的配置加载到 UI PropertyGroup 中

    Args:
        context: Blender context
        pose_bone: 当前选中的 PoseBone

    Returns:
        bool: 是否成功同步
    """
    if not pose_bone or not pose_bone.name.startswith("SET-"):
        print(f"[DEBUG] sync_set_bone_ui: early return - not SET- bone")
        return False

    # 导入避免循环引用
    from . import ui_bone_properties

    set_ui = pose_bone.amazing_set_bone_ui

    # 设置同步标志，防止触发 update 回调
    ui_bone_properties._syncing_set_ui = True
    print(f"[DEBUG] sync_set_bone_ui: starting sync for {pose_bone.name}")

    try:
        for config_type, ui_target in [
            (CONFIG_IK, set_ui.ik),
            (CONFIG_FK, set_ui.fk),
            (CONFIG_IK_CTRL, set_ui.ik_ctrl)
        ]:
            result = load_set_bone_config(pose_bone, config_type)
            print(f"[DEBUG] sync_set_bone_ui {config_type}: config_data={result['config_data'] is not None}, armature_obj={result['armature_obj']}, valid={result['valid']}, ui_bone='{ui_target.bone}'")

            if result["config_data"] is not None:
                if result["armature_obj"] and result["valid"]:
                    # 情况1：armature 和 bone 都有效
                    ui_target.armature = result["armature_obj"]
                    ui_target.bone = result["bone_name"]
                    print(f"[DEBUG] sync_set_bone_ui {config_type}: case 1 - set armature and bone")
                elif result["armature_obj"]:
                    # 情况2：armature 存在但 bone 被删除（失效配置）
                    # 清除持久化配置，因为配置的 bone 已不存在
                    # 同时清空 armature 和 bone，让 UI 恢复"未选择"状态
                    clear_set_bone_config(pose_bone, config_type)
                    ui_target.armature = None  # 清空 armature
                    ui_target.bone = ""
                    print(f"[DEBUG] sync_set_bone_ui {config_type}: case 2 - bone deleted, cleared config and UI")
                else:
                    # 情况3：armature 也不存在（被删除），清除持久化配置
                    clear_set_bone_config(pose_bone, config_type)
                    ui_target.armature = None
                    ui_target.bone = ""
                    print(f"[DEBUG] sync_set_bone_ui {config_type}: case 3 - armature deleted, cleared config")
            else:
                # 情况4：没有持久化配置数据
                # 但 UI PropertyGroup 里可能有值（用户配置存在 UI 但没持久化）
                # 需要检查 UI PropertyGroup 里的 bone 是否仍然有效
                ui_armature = ui_target.armature
                ui_bone = ui_target.bone
                if ui_armature and ui_bone:
                    # UI PropertyGroup 里有值，检查 bone 是否还存在
                    bone_exists = ui_bone in ui_armature.data.bones if ui_armature.data else False
                    if not bone_exists:
                        # UI 里配置的 bone 已被删除，清空 UI
                        ui_target.armature = None
                        ui_target.bone = ""
                        print(f"[DEBUG] sync_set_bone_ui {config_type}: case 4 - UI bone deleted, cleared UI")
                    else:
                        print(f"[DEBUG] sync_set_bone_ui {config_type}: case 4 - UI bone exists, preserved")
                else:
                    # UI 也是空的，无需处理
                    print(f"[DEBUG] sync_set_bone_ui {config_type}: case 4 - no config and no UI, preserved")

        return True
    except Exception as e:
        print(f"[ERROR] 同步 SET-骨骼 UI 失败: {e}")
        return False
    finally:
        ui_bone_properties._syncing_set_ui = False
        print(f"[DEBUG] sync_set_bone_ui: finished sync")


def mirror_set_bone_configs(source_pb, mirror_pb, arm_obj):
    """镜像 SET-骨骼的 IK/FK/IK_CTRL 配置到镜像骨骼

    从源 SET-骨骼的 UI PropertyGroup 读取配置，翻转 bone 名称后写入镜像骨骼。
    配置存在于 amazing_set_bone_ui.{ik,fk,ik_ctrl}.bone 中。

    Args:
        source_pb: 源 SET- PoseBone (如 SET-Leg.L)
        mirror_pb: 镜像 SET- PoseBone (如 SET-Leg.R)
        arm_obj: 骨骼所属的 armature 对象

    Returns:
        dict: {
            'mirrored': int,       # 成功镜像的配置数量
            'missing': list[str],  # 翻转后不存在的骨骼名称列表
        }
    """
    result = {
        'mirrored': 0,
        'missing': [],
    }

    if not arm_obj:
        print("[WARNING] mirror_set_bone_configs: arm_obj 为 None，跳过镜像")
        return result

    # 获取镜像骨骼的 dependent bones 列表（已被 Step 2 正确镜像）
    mirror_dependents = utils_bone_data.get_dependent_bones(mirror_pb)
    mirror_dep_names = {dep['bone_name'] for dep in mirror_dependents}

    # 从 UI PropertyGroup 读取源配置
    source_ui = getattr(source_pb, 'amazing_set_bone_ui', None)
    if not source_ui:
        print("[WARNING] mirror_set_bone_configs: source_pb 没有 amazing_set_bone_ui")
        return result

    mirror_ui = getattr(mirror_pb, 'amazing_set_bone_ui', None)
    if not mirror_ui:
        print("[WARNING] mirror_set_bone_configs: mirror_pb 没有 amazing_set_bone_ui")
        return result

    for config_type in [CONFIG_IK, CONFIG_FK, CONFIG_IK_CTRL]:
        ui_target = getattr(source_ui, config_type, None)
        if not ui_target:
            continue

        source_bone_name = ui_target.bone or ""
        if not source_bone_name:
            continue

        # 翻转 bone 名称
        mirrored_bone_name = utils_bone_data.flip_bone_name(source_bone_name)

        # 如果翻转后名称相同（无左右标识），跳过
        if mirrored_bone_name == source_bone_name:
            continue

        # 检查翻转后的骨骼是否在镜像 SET-骨骼的 dependent bones 中
        if mirrored_bone_name not in mirror_dep_names:
            result['missing'].append(f"{config_type}:{mirrored_bone_name}")
            print(f"[WARNING] 镜像配置 {config_type}: '{mirrored_bone_name}' 不在 dependent bones 中，跳过")
            continue

        # 写入镜像 SET-骨骼的 UI PropertyGroup 和 PoseBone 持久化
        mirror_target = getattr(mirror_ui, config_type, None)
        if mirror_target:
            mirror_target.armature = ui_target.armature
            mirror_target.bone = mirrored_bone_name
            # 同时持久化到 PoseBone custom property，确保 sync_set_bone_ui 能读取
            save_set_bone_config(mirror_pb, config_type, ui_target.armature, mirrored_bone_name)
            result['mirrored'] += 1
            print(f"[INFO] 镜像配置 {config_type}: {source_bone_name} -> {mirrored_bone_name}")

    return result
