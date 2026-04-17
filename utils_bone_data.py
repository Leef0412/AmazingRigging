import bpy
import uuid
import json

# 自定义属性键常量（以 _ 开头，减少在 Custom Properties 面板中的可见性）
KEY_SETTINGS_BONE = "_amazing_settings_bone"
KEY_SETTINGS_ARMATURE = "_amazing_settings_armature"
KEY_SETTINGS_ARMATURE_UUID = "_amazing_settings_armature_uuid"
KEY_DEPENDENT_BONES = "_amazing_dependent_bones"

# 旧版属性键名（用于迁移）
_KEY_SETTINGS_BONE_OLD = "amazing_settings_bone"
_KEY_SETTINGS_ARMATURE_OLD = "amazing_settings_armature"
_KEY_SETTINGS_ARMATURE_UUID_OLD = "amazing_settings_armature_uuid"
_KEY_DEPENDENT_BONES_OLD = "amazing_dependent_bones"

# 旧键 → 新键 映射
_MIGRATION_MAP = {
    _KEY_SETTINGS_BONE_OLD: KEY_SETTINGS_BONE,
    _KEY_SETTINGS_ARMATURE_OLD: KEY_SETTINGS_ARMATURE,
    _KEY_SETTINGS_ARMATURE_UUID_OLD: KEY_SETTINGS_ARMATURE_UUID,
    _KEY_DEPENDENT_BONES_OLD: KEY_DEPENDENT_BONES,
}

# 所有内部键名（新旧都包含，用于过滤显示）
INTERNAL_KEYS = {
    KEY_SETTINGS_BONE, KEY_SETTINGS_ARMATURE, KEY_SETTINGS_ARMATURE_UUID, KEY_DEPENDENT_BONES,
    _KEY_SETTINGS_BONE_OLD, _KEY_SETTINGS_ARMATURE_OLD, _KEY_SETTINGS_ARMATURE_UUID_OLD, _KEY_DEPENDENT_BONES_OLD,
}


def sort_bones_alphabetical(bones):
    """按字母顺序排序骨骼列表
    
    Args:
        bones: Blender bones 集合或列表
    
    Returns:
        按字母顺序排序的骨骼列表
    """
    return sorted(bones, key=lambda b: b.name)


def get_pose_bone(obj, bone_name):
    """获取 PoseBone 对象"""
    if not obj or obj.type != 'ARMATURE' or not bone_name:
        return None
    return obj.pose.bones.get(bone_name)


def find_armature_obj_by_uuid(uuid_str):
    """通过 Armature 数据 UUID 查找场景中的 Armature 对象"""
    if not uuid_str:
        return None
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and hasattr(obj.data, 'uuid') and obj.data.uuid == uuid_str:
            return obj
    return None


def get_or_create_armature_uuid(arm_data):
    """获取或创建 armature 的 UUID"""
    if not arm_data:
        return ""

    current_uuid = getattr(arm_data, 'uuid', '')
    if not current_uuid:
        arm_data.uuid = str(uuid.uuid4())
        current_uuid = arm_data.uuid

    return current_uuid


def find_armature_by_uuid(uuid_str):
    """通过 UUID 查找 armature 数据块"""
    if not uuid_str:
        return None

    for arm in bpy.data.armatures:
        if getattr(arm, 'uuid', '') == uuid_str:
            return arm
    return None


def _parse_dependent_bones(pose_bone):
    """解析 dependent_bones JSON 数据"""
    data_str = pose_bone.get(KEY_DEPENDENT_BONES, "")
    if not data_str:
        # 兼容旧键名
        data_str = pose_bone.get(_KEY_DEPENDENT_BONES_OLD, "")
    if not data_str:
        return []
    try:
        return json.loads(data_str)
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize_dependent_bones(dependent_list):
    """序列化 dependent_bones 为 JSON 字符串"""
    return json.dumps(dependent_list, ensure_ascii=False)


def _add_dependent_bone(target_pose_bone, source_pose_bone, source_arm_obj):
    """在主导骨骼上添加从属骨骼引用"""
    dependent_list = _parse_dependent_bones(target_pose_bone)

    # 如果 source_arm_obj 为 None，尝试从 source_pose_bone 获取
    if source_arm_obj is None and hasattr(source_pose_bone, 'id_data'):
        source_arm_obj = source_pose_bone.id_data

    # 构建新的依赖记录
    new_entry = {
        "bone_name": source_pose_bone.name,
        "armature_name": source_arm_obj.data.name if source_arm_obj else "",
        "armature_uuid": get_or_create_armature_uuid(source_arm_obj.data) if source_arm_obj else ""
    }

    # 检查是否已存在（避免重复）
    for entry in dependent_list:
        if (entry.get("bone_name") == new_entry["bone_name"] and
            entry.get("armature_uuid") == new_entry["armature_uuid"]):
            return  # 已存在，不重复添加

    dependent_list.append(new_entry)
    target_pose_bone[KEY_DEPENDENT_BONES] = _serialize_dependent_bones(dependent_list)


def _remove_dependent_bone(target_bone_info, source_pose_bone, target_pose_bone=None):
    """从主导骨骼上移除指定的从属骨骼引用

    参数:
        target_bone_info: 主导骨骼信息字典
        source_pose_bone: 从属 PoseBone 对象
        target_pose_bone: 可选，主导 PoseBone 对象（如果已知）
    """
    # 查找主导 PoseBone
    if not target_pose_bone:
        arm_obj = find_armature_obj_by_uuid(target_bone_info['armature_uuid'])
        if not arm_obj:
            arm_data = bpy.data.armatures.get(target_bone_info.get('armature_name', ''))
            if arm_data:
                for obj in bpy.data.objects:
                    if obj.type == 'ARMATURE' and obj.data == arm_data:
                        arm_obj = obj
                        break
        if not arm_obj:
            return False
        target_pose_bone = arm_obj.pose.bones.get(target_bone_info['bone_name'])
        if not target_pose_bone:
            return False

    dependent_list = _parse_dependent_bones(target_pose_bone)

    # 获取从属骨骼所属 armature 的 UUID
    source_arm_uuid = ""
    if hasattr(source_pose_bone, 'id_data') and source_pose_bone.id_data:
        source_arm_uuid = get_or_create_armature_uuid(source_pose_bone.id_data.data)

    # 移除匹配的记录
    filtered_list = [
        entry for entry in dependent_list
        if not (entry.get("bone_name") == source_pose_bone.name and
                entry.get("armature_uuid") == source_arm_uuid)
    ]

    if len(filtered_list) != len(dependent_list):
        target_pose_bone[KEY_DEPENDENT_BONES] = _serialize_dependent_bones(filtered_list)
        return True
    return False


def set_settings_bone(pose_bone, settings_bone_name, settings_arm_obj=None, source_arm_obj=None, source_pose_bone=None, target_pose_bone=None):
    """
    设置 PoseBone 的 settings bone

    参数:
        pose_bone: 目标 PoseBone 对象
        settings_bone_name: settings bone 的名称
        settings_arm_obj: settings bone 所属的 armature 对象
        source_arm_obj: 当前 bone 所属的 armature 对象（用于确保 UUID）
        source_pose_bone: 从属 PoseBone 对象（用于写入反向引用）
        target_pose_bone: 可选，主导 PoseBone 对象（用于写入反向引用）
    """
    if settings_arm_obj is None:
        settings_arm_obj = source_arm_obj

    # 防止骨骼引用自身作为 settings bone
    if (source_arm_obj and settings_arm_obj and
        source_arm_obj.data == settings_arm_obj.data and
        source_arm_obj.name == settings_arm_obj.name and
        pose_bone.name == settings_bone_name):
        return False

    # 确保 armature 有 UUID
    settings_arm_uuid = get_or_create_armature_uuid(settings_arm_obj.data)

    # 在 pose_bone 上存储 settings bone 信息
    pose_bone[KEY_SETTINGS_BONE] = settings_bone_name
    pose_bone[KEY_SETTINGS_ARMATURE] = settings_arm_obj.data.name
    pose_bone[KEY_SETTINGS_ARMATURE_UUID] = settings_arm_uuid

    # 清理旧键名（如果存在）
    for old_key in (_KEY_SETTINGS_BONE_OLD, _KEY_SETTINGS_ARMATURE_OLD, _KEY_SETTINGS_ARMATURE_UUID_OLD):
        if old_key in pose_bone:
            del pose_bone[old_key]

    # 在 settings_bone 上添加反向引用
    if source_pose_bone:
        settings_pb = target_pose_bone or settings_arm_obj.pose.bones.get(settings_bone_name)
        if settings_pb:
            _add_dependent_bone(settings_pb, source_pose_bone, source_arm_obj)

    return True


def get_settings_bone_info(pose_bone):
    """
    获取 PoseBone 的 settings bone 信息

    返回:
        dict: {
            'bone_name': str,
            'armature_name': str,
            'armature_uuid': str
        }
        或 None（如果未设置）
    """
    settings_bone_name = pose_bone.get(KEY_SETTINGS_BONE, "")
    if not settings_bone_name:
        # 兼容旧键名
        settings_bone_name = pose_bone.get(_KEY_SETTINGS_BONE_OLD, "")
    if not settings_bone_name:
        return None

    return {
        'bone_name': settings_bone_name,
        'armature_name': pose_bone.get(KEY_SETTINGS_ARMATURE, "") or pose_bone.get(_KEY_SETTINGS_ARMATURE_OLD, ""),
        'armature_uuid': pose_bone.get(KEY_SETTINGS_ARMATURE_UUID, "") or pose_bone.get(_KEY_SETTINGS_ARMATURE_UUID_OLD, "")
    }


def get_settings_bone_object(pose_bone):
    """
    获取 settings bone 的 PoseBone 对象

    返回:
        PoseBone 对象或 None
    """
    info = get_settings_bone_info(pose_bone)
    if not info:
        return None

    # 查找 armature 对象
    arm_obj = find_armature_obj_by_uuid(info['armature_uuid'])
    if not arm_obj:
        # 尝试通过名称查找（向后兼容）
        arm_data = bpy.data.armatures.get(info['armature_name'])
        if arm_data:
            for obj in bpy.data.objects:
                if obj.type == 'ARMATURE' and obj.data == arm_data:
                    arm_obj = obj
                    break

    if not arm_obj:
        return None

    # 返回 PoseBone 对象
    return arm_obj.pose.bones.get(info['bone_name'])


def clear_settings_bone(pose_bone, target_bone_info=None, target_pose_bone=None):
    """
    清除 PoseBone 的 settings bone 信息

    参数:
        pose_bone: 要清除的 PoseBone 对象
        target_bone_info: 主导骨骼信息（用于移除反向引用）
        target_pose_bone: 可选，主导 PoseBone 对象（用于移除反向引用）
    """
    # 从主导骨骼上移除此从属骨骼引用
    if target_bone_info:
        _remove_dependent_bone(target_bone_info, pose_bone, target_pose_bone=target_pose_bone)

    # 清理新键名
    if KEY_SETTINGS_BONE in pose_bone:
        del pose_bone[KEY_SETTINGS_BONE]
    if KEY_SETTINGS_ARMATURE in pose_bone:
        del pose_bone[KEY_SETTINGS_ARMATURE]
    if KEY_SETTINGS_ARMATURE_UUID in pose_bone:
        del pose_bone[KEY_SETTINGS_ARMATURE_UUID]

    # 同时清理旧键名（如果存在）
    if _KEY_SETTINGS_BONE_OLD in pose_bone:
        del pose_bone[_KEY_SETTINGS_BONE_OLD]
    if _KEY_SETTINGS_ARMATURE_OLD in pose_bone:
        del pose_bone[_KEY_SETTINGS_ARMATURE_OLD]
    if _KEY_SETTINGS_ARMATURE_UUID_OLD in pose_bone:
        del pose_bone[_KEY_SETTINGS_ARMATURE_UUID_OLD]

    return True


def get_dependent_bones(pose_bone):
    """获取主导骨骼的所有从属骨骼引用"""
    return _parse_dependent_bones(pose_bone)


def cleanup_dependent_bones(master_pose_bone, master_arm_obj=None):
    """
    当主导骨骼被删除时，清理所有从属骨骼的设置

    参数:
        master_pose_bone: 被删除的主导 PoseBone 对象
        master_arm_obj: 主导骨骼所属的 armature 对象

    返回:
        int: 清理的从属骨骼数量
    """
    dependent_list = _parse_dependent_bones(master_pose_bone)

    if not dependent_list:
        return 0

    cleaned_count = 0

    for dep in dependent_list:
        dep_bone_name = dep.get('bone_name', '')
        dep_arm_name = dep.get('armature_name', '')
        dep_arm_uuid = dep.get('armature_uuid', '')

        if not dep_bone_name:
            continue

        # 查找从属骨骼所属的 armature 对象
        dep_arm_obj = None
        if dep_arm_uuid:
            dep_arm_obj = find_armature_obj_by_uuid(dep_arm_uuid)
        if not dep_arm_obj and dep_arm_name:
            arm_data = bpy.data.armatures.get(dep_arm_name)
            if arm_data:
                for obj in bpy.data.objects:
                    if obj.type == 'ARMATURE' and obj.data == arm_data:
                        dep_arm_obj = obj
                        break

        if not dep_arm_obj:
            continue

        # 查找从属 PoseBone
        dep_pb = dep_arm_obj.pose.bones.get(dep_bone_name)
        if not dep_pb:
            continue

        # 检查该骨骼是否确实指向当前主导骨骼
        settings_info = get_settings_bone_info(dep_pb)
        if settings_info:
            master_bone_name = master_pose_bone.name
            master_arm_name_actual = master_arm_obj.data.name if master_arm_obj else ""

            if (settings_info['bone_name'] == master_bone_name and
                settings_info['armature_name'] == master_arm_name_actual):
                clear_settings_bone(dep_pb)
                cleaned_count += 1

    return cleaned_count


def has_settings_bone(pose_bone):
    """检查 PoseBone 是否设置了 settings bone"""
    if (KEY_SETTINGS_BONE in pose_bone and pose_bone[KEY_SETTINGS_BONE]):
        return True
    if (_KEY_SETTINGS_BONE_OLD in pose_bone and pose_bone[_KEY_SETTINGS_BONE_OLD]):
        return True
    return False


def get_selected_bones_with_data(context):
    """
    获取当前选中的 PoseBones 及其 settings bone 信息

    返回:
        list of dict: [
            {
                'bone_name': str,
                'pose_bone': PoseBone,
                'settings_info': dict or None
            }
        ]
    """
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return []

    result = []

    for pb in context.selected_pose_bones:
        settings_info = get_settings_bone_info(pb)
        result.append({
            'bone_name': pb.name,
            'pose_bone': pb,
            'settings_info': settings_info
        })

    return result


def migrate_bone_properties():
    """迁移旧版属性键名和存储位置。

    在插件注册时通过定时器延迟调用。扫描所有 armature 对象：
    1. 将旧键名（amazing_settings_bone 等）迁移到新键名（_amazing_settings_bone 等）
    2. 将数据从 Bone（arm_data.bones）迁移到 PoseBone（obj.pose.bones）
    """
    try:
        migrated_count = 0

        for obj in bpy.data.objects:
            if obj.type != 'ARMATURE':
                continue
            arm_data = obj.data

            for bone in arm_data.bones:
                pb = obj.pose.bones.get(bone.name)
                if not pb:
                    continue

                # 迁移旧键名（在 Bone 上）→ 新键名（在 PoseBone 上）
                for old_key, new_key in _MIGRATION_MAP.items():
                    if old_key in bone:
                        pb[new_key] = bone[old_key]
                        del bone[old_key]
                        migrated_count += 1

                # 也迁移已用新键名但存在 Bone 上的数据
                for new_key in (KEY_SETTINGS_BONE, KEY_SETTINGS_ARMATURE, KEY_SETTINGS_ARMATURE_UUID, KEY_DEPENDENT_BONES):
                    if new_key in bone:
                        if new_key not in pb:
                            pb[new_key] = bone[new_key]
                            migrated_count += 1
                        del bone[new_key]

                # 也检查 PoseBone 上的旧键名
                for old_key, new_key in _MIGRATION_MAP.items():
                    if old_key in pb:
                        pb[new_key] = pb[old_key]
                        del pb[old_key]
                        migrated_count += 1

        if migrated_count > 0:
            print(f"[AmazingRigging] 迁移了 {migrated_count} 个属性（键名+存储位置）")
    except Exception as e:
        print(f"[AmazingRigging] 属性迁移异常: {e}")
        import traceback
        traceback.print_exc()

    return None  # 定时器调用时返回 None 表示只执行一次
