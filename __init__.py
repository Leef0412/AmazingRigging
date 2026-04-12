bl_info = {
    "name": "Amazing Rigging",
    "author": "Li Fang",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Amazing Rigging",
    "description": "Displays all Bone Collections of the active armature when a bone is selected",
    "category": "Rigging",
}

# 导入子模块
from bpy.app.handlers import persistent
import bpy
import uuid
from . import ui_panel
from . import ui_layer_editor
from . import op_scripts
from . import ui_bone_properties
from . import utils_bone_data

_msgbus_owner = object()

# 存储已知的 collection 名称，用于检测变化
_collection_name_cache = {}

# 存储每个 armature 的骨骼名称集合，用于检测骨骼删除
_bone_names_cache = {}  # {armature_name: {bone_name1, bone_name2, ...}}

# 骨骼删除处理标志，避免重复执行
_processing_bone_deletion = False

# 定时器状态管理
_timer_active = False
_poll_count = 0  # 轮询计数器
_processing_collection_change = False

_last_active_armature = None

# 属性迁移标志（确保只执行一次）
_migration_done = False

def on_selection_change():
    global _last_active_armature

    try:
        obj = bpy.context.object

        current_armature = None
        if obj and obj.type == 'ARMATURE':
            current_armature = obj.data

        if current_armature != _last_active_armature:
            if _last_active_armature is not None:
                print(f"\n[DEBUG] checked switch armature:")
                print(f"  - From: {_last_active_armature.name}")
                print(f"  - To: {current_armature.name if current_armature else 'None'}")

                if hasattr(_last_active_armature, 'amazing_props'):
                    if _last_active_armature.amazing_props.editing_item_key:
                        print(f"  - Old armature editing_key: '{_last_active_armature.amazing_props.editing_item_key}'")
                    if _last_active_armature.amazing_props.editing_pocket_key:
                        print(f"  - Old armature editing_pocket_key: '{_last_active_armature.amazing_props.editing_pocket_key}'")

            if current_armature is not None and hasattr(current_armature, 'amazing_props'):
                if current_armature.amazing_props.editing_item_key:
                    print(f"  - New armature editing_key: '{current_armature.amazing_props.editing_item_key}")
                    current_armature.amazing_props.editing_item_key = ""

                if current_armature.amazing_props.editing_pocket_key:
                    print(f"  - New armature editing_pocket_key: '{current_armature.amazing_props.editing_pocket_key}")
                    current_armature.amazing_props.editing_pocket_key = ""

                for area in bpy.context.screen.areas:
                    area.tag_redraw()

            _last_active_armature = current_armature

    except Exception as e:
        print(f"[ERROR] on_selection_change Except: {e}")
        import traceback
        traceback.print_exc()

def reindex_rows(arm_data, grid_data):
    """重新索引行号（与 ui_layer_editor.AMAZING_RIGGING_OT_remove_from_grid.reindex_rows 一致）"""
    rows_dict = {}
    for item in grid_data:
        if item.row not in rows_dict:
            rows_dict[item.row] = []
        rows_dict[item.row].append(item)
    
    sorted_rows = sorted(rows_dict.keys())
    
    old_to_new_row = {}
    for new_row_idx, old_row_idx in enumerate(sorted_rows):
        old_to_new_row[old_row_idx] = new_row_idx
        for item in rows_dict[old_row_idx]:
            item.row = new_row_idx
    
    for pocket in arm_data.amazing_bone_pockets:
        if pocket.row in old_to_new_row:
            pocket.row = old_to_new_row[pocket.row]


def on_collection_rename_for_armature(old_names, new_names, obj):
    """处理特定 armature object 的 collection 变化"""
    global _processing_collection_change

    if _processing_collection_change:
        print("[DEBUG] 正在处理 collection 变化,跳过重复调用")
        return

    _processing_collection_change = True

    try:
        print("=== [DEBUG] on_collection_rename 被调用 ===")
        print(f"旧名称集合: {old_names}")
        print(f"新名称集合: {new_names}")
        print(f"object: {obj}")
    
        arm_data = obj.data

        grid_data = arm_data.amazing_grid_data
        deform_grid_data = arm_data.amazing_deform_grid_data
        b_cols = arm_data.collections
        print(f"grid_data 项数: {len(grid_data)}")
        print(f"deform_grid_dat 项数: {len(deform_grid_data)}")
        print(f"b_collections 数量: {len(b_cols)}")
        print(f"b_collections 列表: {[bc.name for bc in b_cols]}")
    
        # 找出被删除的名称（旧名称中不在新名称中的）
        removed_names = old_names - new_names
        # 找出新增的名称（新名称中不在旧名称中的）
        added_names = new_names - old_names
    
        print(f"\n被删除的名称: {removed_names}")
        print(f"新增的名称: {added_names}")
    
        # 判断是重命名还是纯删除
        is_rename = (len(removed_names) == 1 and len(added_names) == 1)
    
        if is_rename:
            # 处理重命名
            old_name = list(removed_names)[0]
            new_name = list(added_names)[0]
            print(f"\n检测到重命名: '{old_name}' -> '{new_name}'")

            # 更新所有匹配的 item.name
            items_updated = []
            for item in grid_data:
                print(f"\n检查 item: name='{item.name}', row={item.row}, col={item.col}, note='{item.note}'")
                if item.name == old_name:
                    print(f"  -> 匹配! 更新: '{item.name}' -> '{new_name}'")
                    item.name = new_name
                    items_updated.append(item)
                else:
                    print(f"  -> 不匹配，跳过")

            for item in deform_grid_data:
                print(f"\n检查 deform_grid_data item: name='{item.name}, row={item.row}, col={item.col}, note='{item.note}'")
                if item.name == old_name:
                    print(f"  - 匹配! 更新: '{item.name} -> '{new_name}'")
                    item.name = new_name
                    items_updated.append(item)
                else:
                    print(f"  - 不匹配，跳过")

            print(f"\n更新了 {len(items_updated)} 个项")
        
            if items_updated:
                print("[DEBUG] 执行 UI 重绘")
                for area in bpy.context.screen.areas:
                    area.tag_redraw()
            else:
                print("[DEBUG] 没有需要更新的项")
    
        # 处理纯删除（不是重命名）
        elif removed_names:
            items_to_remove_grid = []
            items_to_remove_deform = []

            for removed_name in removed_names:
                print(f"\n处理被删除的 collection: '{removed_name}'")
                # 找出所有匹配的 item 索引
                for i, item in enumerate(grid_data):
                    if item.name == removed_name:
                        print(f"  -> [grid_data] 找到要删除的 item: row={item.row}, col={item.col}, note='{item.note}'")
                        items_to_remove_grid.append(i)

                for i, item in enumerate(deform_grid_data):
                    if item.name == removed_name:
                        print(f"  -> [deform_grid_data] 找到要删除的 item: row={item.row}, col={item.col}, note='{item.note}'")
                        items_to_remove_deform.append(i)
        
            # 从后往前删除，避免索引变化
            if items_to_remove_grid:
                print(f"\n删除 {len(items_to_remove_grid)} 个 item")
                for index in reversed(sorted(items_to_remove_grid)):
                    grid_data.remove(index)

                rows_dict = {}
                for item in grid_data:
                    if item.row not in rows_dict:
                        rows_dict[item.row] = []
                    rows_dict[item.row].append(item)

                sorted_rows = sorted(rows_dict.keys())
                old_to_new_row = {}
                for new_row_idx, old_row_idx in enumerate(sorted_rows):
                    old_to_new_row[old_row_idx] = new_row_idx
                    for item in rows_dict[old_row_idx]:
                        item.row = new_row_idx

            if items_to_remove_deform:
                print(f"\n从 deform_grid_data 删除 {len(items_to_remove_deform)} 个 item")
                for index in reversed(sorted(items_to_remove_deform)):
                    deform_grid_data.remove(index)

            if arm_data.amazing_props.editing_item_key:
                arm_data.amazing_props.editing_item_key = ""

            if items_to_remove_grid or items_to_remove_deform:
                print("[DEBUG] 执行 UI 重绘")
                bpy.context.view_layer.update()
                for area in bpy.context.screen.areas:
                    area.tag_redraw()

        if not removed_names and not added_names:
            print("[DEBUG] 没有变化")
        elif not removed_names and added_names:
            print(f"[DEBUG] 仅新增 collection: {added_names}")
        elif len(removed_names) > 1 or len(added_names) > 1:
            print(f"[DEBUG] 复杂操作 (删除:{len(removed_names)}, 新增:{len(added_names)})")

        print("=== [DEBUG] on_collection_rename 结束 ===\n")
    except Exception as e:
        print(f"[ERROR] on_collection_rename_for_armature 异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _processing_collection_change = False


def check_bone_deletions():
    """检测骨骼删除并清理从属骨骼引用"""
    global _bone_names_cache, _processing_bone_deletion
    
    # 避免重复执行
    if _processing_bone_deletion:
        return
    
    try:
        deletion_detected = False
        
        for arm_data in bpy.data.armatures:
            arm_name = arm_data.name
            
            # 获取当前骨骼名称集合
            current_bone_names = {bone.name for bone in arm_data.bones}
            
            # 初始化缓存
            if arm_name not in _bone_names_cache:
                _bone_names_cache[arm_name] = current_bone_names
                continue
            
            cached_bone_names = _bone_names_cache[arm_name]
            
            # 检测删除的骨骼
            deleted_bones = cached_bone_names - current_bone_names
            
            if deleted_bones:
                deletion_detected = True
                print(f"[DEBUG] 检测到骨骼删除: {arm_name} -> {deleted_bones}")
                
                # 更新缓存
                _bone_names_cache[arm_name] = current_bone_names
        
        # 如果检测到删除，执行清理
        if deletion_detected:
            _processing_bone_deletion = True
            try:
                cleanup_invalid_references()
            finally:
                _processing_bone_deletion = False
    
    except Exception as e:
        print(f"[ERROR] check_bone_deletions 异常: {e}")
        import traceback
        traceback.print_exc()
        _processing_bone_deletion = False


def cleanup_invalid_references():
    """清理所有无效的 settings bone 引用（基于 PoseBone）"""
    from . import utils_bone_data

    try:
        cleaned_count = 0

        for obj in bpy.data.objects:
            if obj.type != 'ARMATURE':
                continue
            for pb in obj.pose.bones:
                settings_info = utils_bone_data.get_settings_bone_info(pb)

                if not settings_info:
                    continue

                # 验证 settings bone 是否仍然存在
                settings_pb = utils_bone_data.get_settings_bone_object(pb)

                if settings_pb is None:
                    # settings bone 已不存在，清除引用
                    print(f"[DEBUG] 清理无效引用: {obj.name}/{pb.name} -> {settings_info['armature_name']}/{settings_info['bone_name']} (已删除)")
                    utils_bone_data.clear_settings_bone(pb)
                    cleaned_count += 1

        if cleaned_count > 0:
            print(f"[DEBUG] 共清理了 {cleaned_count} 个无效的 settings bone 引用")
            # 触发 UI 刷新
            for area in bpy.context.screen.areas:
                area.tag_redraw()

    except Exception as e:
        print(f"[ERROR] cleanup_invalid_references 异常: {e}")
        import traceback
        traceback.print_exc()


@persistent
def depsgraph_update_handler(scene):
    """检测 Bone Collection 重命名或删除，以及选择变化"""
    global _migration_done
    try:
        obj = bpy.context.object

        # 首次场景更新时执行属性迁移（比定时器更可靠）
        if not _migration_done:
            try:
                utils_bone_data.migrate_bone_properties()
                _migration_done = True
            except Exception:
                pass

        on_selection_change()
        
        # 同步骨骼选择到 UI 状态
        if obj and obj.type == 'ARMATURE':
            try:
                from . import ui_bone_properties
                ui_bone_properties.sync_ui_to_selected_bone(scene)
            except Exception as e:
                print(f"[ERROR] sync_ui_to_selected_bone 异常: {e}")
                import traceback
                traceback.print_exc()
        
        # 检测骨骼删除并清理无效引用
        check_bone_deletions()

        if obj and obj.type == 'ARMATURE' and not _timer_active:
            ensure_timer_running()
    except Exception as e:
        print(f"[ERROR] depsgraph_update_handler 异常: {e}")


def check_collection_changes():
    """检查所有 armature 的 collection 变化"""
    try:
        # 检查所有已缓存的 armature
        armatures_to_check = list(_collection_name_cache.keys())

        # 同时也检查当前活跃的 armature
        obj = bpy.context.object
        if obj and obj.type == 'ARMATURE':
            arm_data = obj.data
            if arm_data.name not in armatures_to_check:
                armatures_to_check.append(arm_data.name)

        for arm_name in armatures_to_check:
            # 尝试从 bpy.data 中找到这个 armature
            arm_data = bpy.data.armatures.get(arm_name)
            if not arm_data:
                # armature 已被删除，清理缓存
                print(f"[DEBUG] Armature '{arm_name}' 已被删除，清理缓存")
                del _collection_name_cache[arm_name]
                continue

            if not hasattr(arm_data, "amazing_grid_data") or not hasattr(arm_data, "collections"):
                continue

            # 检查是否有新的 armature 需要加入缓存
            if arm_data.name not in _collection_name_cache:
                _collection_name_cache[arm_data.name] = {bc.name for bc in arm_data.collections}
                print(f"[DEBUG] 初始化缓存: {arm_data.name} -> {_collection_name_cache[arm_data.name]}")
                continue

            # 检测名称变化
            current_names = {bc.name for bc in arm_data.collections}
            cached_names = _collection_name_cache[arm_data.name]

            if current_names != cached_names:
                print(f"\n=== [DEBUG] 检测到 collection 变化 (Armature: {arm_name}) ===")
                print(f"  旧: {cached_names}")
                print(f"  新: {current_names}")

                # 保存旧名称用于对比
                old_names = cached_names.copy()

                # 更新缓存
                _collection_name_cache[arm_data.name] = current_names

                # 找到一个使用这个 armature 的 object
                for obj_in_scene in bpy.context.scene.objects:
                    if obj_in_scene.type == 'ARMATURE' and obj_in_scene.data == arm_data:
                        # 调用处理函数
                        on_collection_rename_for_armature(old_names, current_names, obj_in_scene)
                        break

    except Exception as e:
        print(f"[ERROR] check_collection_changes 异常: {e}")
        import traceback
        traceback.print_exc()


def collection_monitor_timer():
    """定时器：定期检测 collection 变化（智能轮询）"""
    global _timer_active, _poll_count

    try:
        _poll_count += 1

        obj = bpy.context.object
        is_armature_selected = (obj is not None and obj.type == "ARMATURE")

        if not is_armature_selected:
            if _timer_active:
                print(f"[DEBUG] 轮询 #{_poll_count}: 当前未选中 armature ===> 停止轮询")
                _timer_active = False
            return None

        if not _collection_name_cache:
            initialize_all_caches()
        else:
            check_collection_changes()

        return 0.5

    except Exception as e:
        print(f"[ERROR] timer 异常: {e}")
        import traceback
        traceback.print_exc()
        _timer_active = False
        return None

@persistent
def on_undo_post(dummy):
    """Undo 后检测变化"""
    print("[DEBUG] on_undo_post 被调用")
    try:
        check_collection_changes()
    except Exception as e:
        print(f"[ERROR] on_undo_post 异常: {e}")

@persistent
def on_load_post(dummy):
    """文件加载后重新注册所有 handlers 并初始化缓存"""
    print("\n=== [DEBUG] on_load_post 被调用 ===")
    
    # 清空缓存和重置状态
    global _timer_active, _poll_count, _processing_collection_change, _migration_done
    _collection_name_cache.clear()
    _timer_active = False
    _poll_count = 0
    _processing_collection_change = False
    _migration_done = False  # 文件加载后需要重新迁移
    
    # 重置 ui_bone_properties 的全局状态
    ui_bone_properties.reset_state()

    # 属性迁移将在首次 depsgraph_update 时执行（_migration_done 已重置为 False）

    print("[DEBUG] 已清空缓存并重置定时器状态")
    
    # 重新请求启动定时器（会在 initialize_all_caches 中实际注册）
    ensure_timer_running()
    print("[DEBUG] 已请求启动智能轮询定时器")
    print("[DEBUG] 定时器将在文件加载完成后自动初始化缓存")
    
    print("=== [DEBUG] on_load_post 结束 ===\n")


def ensure_timer_running():
    """确保定时器正在运行（智能启动）"""
    global _timer_active
    if not _timer_active:
        print("[DEBUG] 启动智能轮询定时器")
        try:
            bpy.app.timers.unregister(collection_monitor_timer)
        except:
            pass
        bpy.app.timers.register(collection_monitor_timer, first_interval=1.0)
        _timer_active = True


def initialize_all_caches():
    """初始化所有 armature 的缓存"""
    print("\n=== [DEBUG] initialize_all_caches 开始 ===")
    try:
        # 确保定时器正在运行
        ensure_timer_running()
        print("[DEBUG] 确保 collection_monitor_timer 已注册")
        
        armature_count = len(bpy.data.armatures)
        print(f"[DEBUG] 找到 {armature_count} 个 armature")
        
        for armature in bpy.data.armatures:
            if hasattr(armature, "amazing_grid_data") and hasattr(armature, "collections"):
                _collection_name_cache[armature.name] = {bc.name for bc in armature.collections}
                print(f"[DEBUG] 初始化缓存: {armature.name} -> {_collection_name_cache[armature.name]}")
            else:
                print(f"[DEBUG] 跳过 {armature.name}: 缺少 amazing_grid_data 或 collections")
        
        print(f"[DEBUG] 当前缓存: {_collection_name_cache}")
    except Exception as e:
        print(f"[DEBUG] initialize_all_caches 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 初始化默认 split rules
    initialize_default_split_rules()
    
    print("=== [DEBUG] initialize_all_caches 结束 ===\n")
    return None  # 只执行一次


def delayed_initialize():
    """延迟初始化包装函数"""
    return initialize_all_caches()


def initialize_default_split_rules():
    """为所有 armature 初始化默认 split rules（如果没有的话）"""
    print("\n=== [DEBUG] initialize_default_split_rules 开始 ===")
    try:
        for armature in bpy.data.armatures:
            if hasattr(armature, "amazing_split_rules"):
                # 只有在规则为空时才初始化
                if len(armature.amazing_split_rules) == 0:
                    print(f"[DEBUG] 为 {armature.name} 初始化默认 split rules")
                    
                    # 创建默认规则 1: Ctrl Bones
                    rule1 = armature.amazing_split_rules.add()
                    rule1.name = "Ctrl Bones"
                    rule1.is_hidden = False
                    prefix1 = rule1.prefixes.add()
                    prefix1.value = "DEF-"
                    exact1 = rule1.exact_matches.add()
                    exact1.value = "Root"

                    # 自动创建 "Other" 规则（用于收集未匹配的骨骼集合）
                    rule_other = armature.amazing_split_rules.add()
                    rule_other.name = "Other"
                    rule_other.is_hidden = False
                    
                    # 迁移逻辑：如果存在旧的 "Other (Deform Bones)" 规则，重命名为 "Other"
                    for rule in armature.amazing_split_rules:
                        if rule.name == "Other (Deform Bones)":
                            rule.name = "Other"
                            print(f"[DEBUG] 已将旧规则 'Other (Deform Bones)' 重命名为 'Other'")
                    
                    print(f"[DEBUG] 已为 {armature.name} 创建 {len(armature.amazing_split_rules)} 个默认规则")
                else:
                    print(f"[DEBUG] {armature.name} 已有 {len(armature.amazing_split_rules)} 个 split rules，跳过初始化")
            else:
                print(f"[DEBUG] 跳过 {armature.name}: 缺少 amazing_split_rules 属性")
    except Exception as e:
        print(f"[ERROR] initialize_default_split_rules 错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("=== [DEBUG] initialize_default_split_rules 结束 ===\n")
    return None  # 只执行一次


# 注册类列表
classes = [
    *ui_panel.classes,
    *ui_layer_editor.classes,
    *op_scripts.classes,
    *ui_bone_properties.classes,
]


def register():
    """注册插件"""
    print("\n=== [DEBUG] register 开始 ===")
    for cls in classes:
        bpy.utils.register_class(cls)
        print(f"注册类: {cls.__name__}")

    bpy.types.Armature.amazing_grid_data = bpy.props.CollectionProperty(type=ui_layer_editor.AMAZING_RIGGING_CollectionItem)
    bpy.types.Armature.amazing_deform_grid_data = bpy.props.CollectionProperty(type=ui_layer_editor.AMAZING_RIGGING_CollectionItem)
    
    # Create collections for each split rule (will be dynamically managed)
    # amazing_grid_data_0, amazing_grid_data_1, etc.
    bpy.types.Armature.amazing_props = bpy.props.PointerProperty(type=ui_layer_editor.AMAZING_RIGGING_ArmatureProperties)
    bpy.types.Armature.amazing_bone_pockets = bpy.props.CollectionProperty(type=ui_layer_editor.AMAZING_RIGGING_Bone_Pocket)
    bpy.types.Armature.amazing_split_rules = bpy.props.CollectionProperty(type=ui_layer_editor.AMAZING_RIGGING_SplitRule)
    
    # 为 Armature 添加 UUID 属性（用于唯一标识）
    bpy.types.Armature.uuid = bpy.props.StringProperty(name="UUID", default="")
    print("属性注册完成")
    
    # 注册 ui_bone_properties 的 Scene 属性
    ui_bone_properties.register()

    # 属性迁移将在首次 depsgraph_update 时执行（比定时器更可靠）
    
    # 延迟初始化 UUID（在 Blender 完全加载后执行）
    def initialize_uuids():
        """延迟初始化所有 armature 的 UUID"""
        try:
            for armature in bpy.data.armatures:
                if not hasattr(armature, 'uuid') or not armature.uuid:
                    armature.uuid = str(uuid.uuid4())
            print("[DEBUG] UUID 初始化完成")
        except Exception as e:
            print(f"[DEBUG] UUID 初始化失败: {e}")
        return None
    
    # 在 0.5 秒后执行 UUID 初始化
    bpy.app.timers.register(initialize_uuids, first_interval=0.5)

    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)
    print("[DEBUG] 已注册 depsgraph_update_handler")

    bpy.app.handlers.undo_post.append(on_undo_post)
    print("[DEBUG] 已注册 undo_post handler")

    bpy.app.handlers.load_post.append(on_load_post)
    print("[DEBUG] 已注册 load_post handler")

    ensure_timer_running()
    print("[DEBUG] 已请求启动智能轮询定时器")
    print("[DEBUG] 定时器将在检测到 armature 时自动初始化缓存")

    print("=== [DEBUG] register 结束 ===\n")


def unregister():
    """卸载插件"""
    print("\n=== [DEBUG] unregister 开始 ===")
    if hasattr(bpy.types.Armature, "amazing_grid_data"):
        del bpy.types.Armature.amazing_grid_data

    if hasattr(bpy.types.Armature, "amazing_deform_grid_data"):
        del bpy.types.Armature.amazing_deform_grid_data

    if hasattr(bpy.types.Armature, "amazing_props"):
        del bpy.types.Armature.amazing_props

    if hasattr(bpy.types.Armature, "amazing_bone_pockets"):
        del bpy.types.Armature.amazing_bone_pockets

    if hasattr(bpy.types.Armature, "amazing_split_rules"):
        del bpy.types.Armature.amazing_split_rules
    
    if hasattr(bpy.types.Armature, "uuid"):
        del bpy.types.Armature.uuid
    
    # 注销 ui_bone_properties 的 Scene 属性
    ui_bone_properties.unregister()

    if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    
    if on_undo_post in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(on_undo_post)
    
    if on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_post)
    
    # 清理定时器
    try:
        bpy.app.timers.unregister(collection_monitor_timer)
        print("[DEBUG] 已移除 collection_monitor_timer")
    except:
        pass

    global _timer_active, _poll_count, _processing_collection_change
    _timer_active = False
    _poll_count = 0
    _processing_collection_change = False
    _collection_name_cache.clear()
    print("缓存、handler 和定时器状态清理完成")

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    print("=== [DEBUG] unregister 结束 ===\n")


if __name__ == "__main__":
    register()