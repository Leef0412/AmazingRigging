import bpy
import uuid
import json

# 自定义属性键常量
KEY_SETTINGS_BONE = "amazing_settings_bone"
KEY_SETTINGS_ARMATURE = "amazing_settings_armature"
KEY_SETTINGS_ARMATURE_UUID = "amazing_settings_armature_uuid"
KEY_DEPENDENT_BONES = "amazing_dependent_bones"


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
    """通过 UUID 查找 armature"""
    if not uuid_str:
        return None
    
    for arm in bpy.data.armatures:
        if getattr(arm, 'uuid', '') == uuid_str:
            return arm
    return None


def _parse_dependent_bones(bone):
    """解析 dependent_bones JSON 数据"""
    data_str = bone.get(KEY_DEPENDENT_BONES, "[]")
    try:
        return json.loads(data_str)
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize_dependent_bones(dependent_list):
    """序列化 dependent_bones 为 JSON 字符串"""
    return json.dumps(dependent_list, ensure_ascii=False)


def _add_dependent_bone(target_bone, source_bone, source_arm_data):
    """在主导骨骼上添加从属骨骼引用"""
    dependent_list = _parse_dependent_bones(target_bone)
    
    # 如果 source_arm_data 为 None，尝试从 source_bone 获取
    if source_arm_data is None and hasattr(source_bone, 'id_data'):
        source_arm_data = source_bone.id_data
    
    # 构建新的依赖记录
    new_entry = {
        "bone_name": source_bone.name,
        "armature_name": source_arm_data.name if source_arm_data else "",
        "armature_uuid": get_or_create_armature_uuid(source_arm_data) if source_arm_data else ""
    }
    
    # 检查是否已存在（避免重复）
    for entry in dependent_list:
        if (entry.get("bone_name") == new_entry["bone_name"] and
            entry.get("armature_uuid") == new_entry["armature_uuid"]):
            return  # 已存在，不重复添加
    
    dependent_list.append(new_entry)
    target_bone[KEY_DEPENDENT_BONES] = _serialize_dependent_bones(dependent_list)


def _remove_dependent_bone(target_bone_info, source_bone, target_bone_for_write=None):
    """从主导骨骼上移除指定的从属骨骼引用
    
    参数:
        target_bone_info: 主导骨骼信息字典
        source_bone: 从属骨骼对象
        target_bone_for_write: 可选，用于写入的主导骨骼对象（Edit Mode 下传入 EditBone）
    """
    # 如果调用方提供了可写对象，直接使用；否则从 armature 查找
    if target_bone_for_write:
        target_bone = target_bone_for_write
    else:
        # 查找主导骨骼对象
        target_arm_data = find_armature_by_uuid(target_bone_info['armature_uuid'])
        if not target_arm_data:
            target_arm_data = bpy.data.armatures.get(target_bone_info['armature_name'])
        
        if not target_arm_data:
            return False
        
        target_bone = target_arm_data.bones.get(target_bone_info['bone_name'])
        if not target_bone:
            return False
    
    dependent_list = _parse_dependent_bones(target_bone)
    
    # 获取从属骨骼所属 armature 的 UUID
    source_arm_uuid = ""
    if hasattr(source_bone, 'id_data') and source_bone.id_data:
        source_arm_uuid = get_or_create_armature_uuid(source_bone.id_data)
    
    # 移除匹配的记录
    filtered_list = [
        entry for entry in dependent_list
        if not (entry.get("bone_name") == source_bone.name and
                entry.get("armature_uuid") == source_arm_uuid)
    ]
    
    if len(filtered_list) != len(dependent_list):
        target_bone[KEY_DEPENDENT_BONES] = _serialize_dependent_bones(filtered_list)
        return True
    return False


def set_settings_bone(bone, settings_bone_name, settings_arm_data=None, source_arm_data=None, source_bone=None, target_bone_for_write=None):
    """
    设置 bone 的 settings bone（直接存储在 bone 对象上）
    
    参数:
        bone: 目标 bone 对象（EditBone/PoseBone/Bone）
        settings_bone_name: settings bone 的名称
        settings_arm_data: settings bone 所属的 armature 数据
        source_arm_data: 当前 bone 所属的 armature 数据（用于确保 UUID）
        source_bone: 从属骨骼对象（用于写入反向引用）
        target_bone_for_write: 可选，用于写入反向引用的主导骨骼对象（Edit Mode 下传入 EditBone）
    """
    if settings_arm_data is None:
        settings_arm_data = source_arm_data
    
    # 确保 armature 有 UUID
    settings_arm_uuid = get_or_create_armature_uuid(settings_arm_data)
    
    # 在 bone 上存储 settings bone 信息
    bone[KEY_SETTINGS_BONE] = settings_bone_name
    bone[KEY_SETTINGS_ARMATURE] = settings_arm_data.name
    bone[KEY_SETTINGS_ARMATURE_UUID] = settings_arm_uuid
    
    # 在 settings_bone 上添加反向引用
    if source_bone:
        # 优先使用调用方提供的可写对象（Edit Mode 下为 EditBone）
        settings_bone_obj = target_bone_for_write or settings_arm_data.bones.get(settings_bone_name)
        if settings_bone_obj:
            _add_dependent_bone(settings_bone_obj, source_bone, source_arm_data)
    
    return True


def get_settings_bone_info(bone):
    """
    获取 bone 的 settings bone 信息
    
    返回:
        dict: {
            'bone_name': str,
            'armature_name': str,
            'armature_uuid': str
        }
        或 None（如果未设置）
    """
    settings_bone_name = bone.get(KEY_SETTINGS_BONE, "")
    if not settings_bone_name:
        return None
    
    return {
        'bone_name': settings_bone_name,
        'armature_name': bone.get(KEY_SETTINGS_ARMATURE, ""),
        'armature_uuid': bone.get(KEY_SETTINGS_ARMATURE_UUID, "")
    }


def get_settings_bone_object(bone):
    """
    获取 settings bone 对象
    
    返回:
        Bone 对象或 None
    """
    info = get_settings_bone_info(bone)
    if not info:
        return None
    
    # 查找 armature
    arm_data = find_armature_by_uuid(info['armature_uuid'])
    if not arm_data:
        # 尝试通过名称查找（向后兼容）
        arm_data = bpy.data.armatures.get(info['armature_name'])
    
    if not arm_data:
        return None
    
    # 返回 bone 对象
    return arm_data.bones.get(info['bone_name'])


def clear_settings_bone(bone, target_bone_info=None, target_bone_for_write=None):
    """
    清除 bone 的 settings bone 信息
    
    参数:
        bone: 要清除的 bone 对象
        target_bone_info: 主导骨骼信息（用于移除反向引用），格式为 get_settings_bone_info() 的返回值
        target_bone_for_write: 可选，用于写入反向引用的主导骨骼对象（Edit Mode 下传入 EditBone）
    """
    # 从主导骨骼上移除此从属骨骼引用
    if target_bone_info:
        _remove_dependent_bone(target_bone_info, bone, target_bone_for_write=target_bone_for_write)
    
    if KEY_SETTINGS_BONE in bone:
        del bone[KEY_SETTINGS_BONE]
    if KEY_SETTINGS_ARMATURE in bone:
        del bone[KEY_SETTINGS_ARMATURE]
    if KEY_SETTINGS_ARMATURE_UUID in bone:
        del bone[KEY_SETTINGS_ARMATURE_UUID]
    
    return True


def get_dependent_bones(bone):
    """获取主导骨骼的所有从属骨骼引用"""
    return _parse_dependent_bones(bone)


def cleanup_dependent_bones(master_bone, master_arm_data=None):
    """
    当主导骨骼被删除时，清理所有从属骨骼的设置
    
    参数:
        master_bone: 被删除的主导骨骼对象（或包含 dependent_bones 数据的 bone）
        master_arm_data: 主导骨骼所属的 armature 数据（可选，用于跨 armature 查找）
    
    返回:
        int: 清理的从属骨骼数量
    """
    dependent_list = _parse_dependent_bones(master_bone)
    
    if not dependent_list:
        return 0
    
    cleaned_count = 0
    
    for dep in dependent_list:
        dep_bone_name = dep.get('bone_name', '')
        dep_arm_name = dep.get('armature_name', '')
        dep_arm_uuid = dep.get('armature_uuid', '')
        
        if not dep_bone_name:
            continue
        
        # 查找从属骨骼所属的 armature
        dep_arm_data = None
        if dep_arm_uuid:
            dep_arm_data = find_armature_by_uuid(dep_arm_uuid)
        if not dep_arm_data and dep_arm_name:
            dep_arm_data = bpy.data.armatures.get(dep_arm_name)
        
        if not dep_arm_data:
            continue
        
        # 查找从属骨骼对象
        dep_bone = dep_arm_data.bones.get(dep_bone_name)
        if not dep_bone:
            continue
        
        # 检查该骨骼是否确实指向当前主导骨骼
        settings_info = get_settings_bone_info(dep_bone)
        if settings_info:
            master_bone_name = master_bone.name
            master_arm_name_actual = master_arm_data.name if master_arm_data else ""
            
            # 验证是否指向当前被删除的主导骨骼
            if (settings_info['bone_name'] == master_bone_name and
                settings_info['armature_name'] == master_arm_name_actual):
                # 清除从属骨骼的设置
                clear_settings_bone(dep_bone)
                cleaned_count += 1
    
    return cleaned_count


def has_settings_bone(bone):
    """检查 bone 是否设置了 settings bone"""
    return KEY_SETTINGS_BONE in bone and bone[KEY_SETTINGS_BONE]


def get_bone_in_mode(obj, bone_name):
    """
    根据当前模式获取 bone 对象
    
    参数:
        obj: armature object
        bone_name: bone 名称
    
    返回:
        EditBone（Edit Mode）/ Bone（其他模式）或 None
    """
    if not obj or obj.type != 'ARMATURE':
        return None
    
    arm_data = obj.data
    
    if obj.mode == 'EDIT':
        return arm_data.edit_bones.get(bone_name)
    else:
        return arm_data.bones.get(bone_name)


def get_selected_bones_with_data(context):
    """
    获取当前选中的 bones 及其 settings bone 信息
    
    返回:
        list of dict: [
            {
                'bone_name': str,
                'bone_object': Bone,
                'settings_info': dict or None
            }
        ]
    """
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return []
    
    arm_data = obj.data
    result = []
    
    # 根据模式获取选中的 bones
    if obj.mode == 'POSE':
        selected_bones = [pb.name for pb in context.selected_pose_bones]
        bone_source = arm_data.bones
    elif obj.mode == 'EDIT':
        selected_bones = [eb.name for eb in context.selected_editable_bones]
        bone_source = arm_data.edit_bones
    else:
        selected_bones = [b.name for b in arm_data.bones if b.select]
        bone_source = arm_data.bones
    
    for bone_name in selected_bones:
        bone = bone_source.get(bone_name)
        if bone:
            settings_info = get_settings_bone_info(bone)
            result.append({
                'bone_name': bone_name,
                'bone_object': bone,
                'settings_info': settings_info
            })
    
    return result
