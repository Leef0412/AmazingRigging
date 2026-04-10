import bpy
from bpy.types import Panel, Operator
from bpy.props import StringProperty, IntProperty
from datetime import datetime

_last_pose_armature = None

# Independent fold state for ui_panel (not shared with Split Bones Rules panel)
_ui_panel_rule_hidden = {}  # {armature_data_name_rule_idx: is_hidden}

# Independent fold state for pockets per rule (not shared across rules)
_ui_panel_pocket_hidden = {}  # {armature_data_name_rule_idx_pocket_row: is_hidden}

class AMAZING_RIGGING_OT_toggle_ui_panel_rule(Operator):
    bl_idname = "armature.amazing_rigging_toggle_ui_panel_rule"
    bl_label = "Toggle UI Panel Rule Visibility"
    bl_description = "Toggle rule visibility in UI panel only"
    bl_options = {'INTERNAL'}

    rule_index: IntProperty()

    def execute(self, context):
        global _ui_panel_rule_hidden
        arm_data = context.active_object.data

        rule_key = f"{arm_data.name}_{self.rule_index}"
        current_hidden = _ui_panel_rule_hidden.get(rule_key, False)
        _ui_panel_rule_hidden[rule_key] = not current_hidden

        for area in context.screen.areas:
            area.tag_redraw()

        status = "expanded" if current_hidden else "collapsed"
        self.report({'INFO'}, f"Rule {self.rule_index} {status}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_toggle_ui_panel_pocket(Operator):
    bl_idname = "armature.amazing_rigging_toggle_ui_panel_pocket"
    bl_label = "Toggle UI Panel Pocket Visibility"
    bl_description = "Toggle pocket visibility in UI panel only"
    bl_options = {'INTERNAL'}

    pocket_row: IntProperty()
    rule_index: IntProperty()

    def execute(self, context):
        global _ui_panel_pocket_hidden
        arm_data = context.active_object.data

        # Use independent fold state per rule
        pocket_key = f"{arm_data.name}_{self.rule_index}_{self.pocket_row}"
        current_hidden = _ui_panel_pocket_hidden.get(pocket_key, False)
        _ui_panel_pocket_hidden[pocket_key] = not current_hidden

        for area in context.screen.areas:
            area.tag_redraw()

        status = "expanded" if current_hidden else "collapsed"
        self.report({'INFO'}, f"Pocket {self.pocket_row} in rule {self.rule_index} {status}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_toggle_bone_collection(Operator):
    bl_idname = "armature.amazing_rigging_toggle_collection"
    bl_label = "Toggle Collection Visibility"
    bl_description = "Toggle bone collection visibility"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: StringProperty()

    def execute(self, context):
        arm_data = context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols and self.collection_name in b_cols:
            b_col = b_cols[self.collection_name]
            b_col.is_visible = not b_col.is_visible

            for area in context.screen.areas:
                area.tag_redraw()

            status = "shown" if b_col.is_visible else "hidden"
            self.report({'INFO'}, f"'{self.collection_name}' {status}")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_show_all(Operator):
    bl_idname = "armature.collection_show_all"
    bl_label = "Show All Collections"
    bl_description = "Show all bone collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols:
            for b_col in b_cols:
                b_col.is_visible = True

            for area in context.screen.areas:
                area.tag_redraw()

            self.report({'INFO'}, "All collections shown")

        return {'FINISHED'}

class AMAZING_RIGGING_OT_hide_all(Operator):
    bl_idname = "armature.collection_hide_all"
    bl_label = "Hide All Collections"
    bl_description = "Hide all bone collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols:
            for b_col in b_cols:
                b_col.is_visible = False

            for area in context.screen.areas:
                area.tag_redraw()

            self.report({'INFO'}, "All collections hidden")

        return {'FINISHED'}

def update_pose_armature_cache(context):
    global _last_pose_armature
    obj = context.active_object

    if obj and obj.type == 'ARMATURE' and obj.mode == 'POSE':
        _last_pose_armature = obj
        print(f"  - [缓存更新] _last_pose_armature = {obj.name}")
    elif obj and obj.type != 'ARMATURE':
        in_pose_mode = False
        for scene_obj in context.scene.objects:
            if scene_obj.type == 'ARMATURE' and scene_obj.mode == 'POSE':
                in_pose_mode = True
                break

        if not in_pose_mode and _last_pose_armature:
            print(f"  - [缓存清空] _last_pose_armature 从 '{_last_pose_armature.name}' 清空为 None")
            _last_pose_armature = None

class AMAZING_RIGGING_PT_main_sidebar(Panel):
    bl_label = "Amazing Rigging"
    bl_idname = "OBJECT_PT_amazing_rigging_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Amazing Rigging"

    @classmethod
    def poll(cls, context):
        return True
        # return context.active_object and context.active_object.type == 'ARMATURE'

    def draw(self, context):
        global _last_pose_armature
        layout = self.layout

        update_pose_armature_cache(context)

        obj = context.active_object

        if not obj:
            layout.label(text="Please select an object", icon='INFO')
            return

        is_armature = obj.type == 'ARMATURE'
        is_pose_mode = is_armature and obj.mode == 'POSE'

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"\n[DEBUG] ui_panel.draw [{timestamp}]:")
        print(f"  - 当前对象: {obj.name}, 类型： {obj.type}")
        print(f"  - 当前模式: {obj.mode if is_armature else 'N/A'}")
        print(f"  - _last_pose_armature: {_last_pose_armature.name if _last_pose_armature else 'None'}")

        target_armature = None
        if is_armature:
            target_armature = obj
            print(f"  - target_armature: {obj.name} (来自当前选中)")
        elif _last_pose_armature:
            target_armature = _last_pose_armature
            print(f"  - target_armature: {_last_pose_armature.name} (来自缓存)")
        else:
            print(f"  - target_armature: None")

        if target_armature:
            layout.label(text=f"Active Armature: {target_armature.name}", icon='ARMATURE_DATA')
        layout.separator()

        if not target_armature:
            return

        arm_data = target_armature.data

        print(f"  - arm_data: {arm_data}")
        print(f"  - arm_data 类型: {type(arm_data)}")

        grid_data = getattr(arm_data, "amazing_grid_data", [])
        pockets = getattr(arm_data, "amazing_bone_pockets", [])
        pocket_rows = {pocket.row for pocket in pockets}

        print(f"  - grid_data: {grid_data}")
        print(f"  - grid_data 长度: {len(grid_data)}")
        print(f"  - separators 数量: {len(pockets)}")

        if not grid_data or len(grid_data) == 0:
            layout.label(text="No Amazing Rigging UI data found!")
            layout.label(text="Please initialize in Armature settings", icon='ERROR')
            print(f"  - [Warning] grid_data 为空,无法显示UI")
            return

        layout.label(text="Collection Options", icon='FILE_SCRIPT')
        row_scripts_1 = layout.row()
        row_scripts_1.operator("armature.amazing_rigging_clean_deform", text="Clean Deform", icon='BRUSH_DATA')

        active_obj = context.active_object
        current_mode = active_obj.mode if active_obj else 'OBJECT'
        if current_mode == 'WEIGHT_PAINT':
            row_scripts_1.operator("armature.amazing_rigging_goto_pose", text="Pose Mode", icon='POSE_HLT')
        else:
            row_scripts_1.operator("armature.amazing_rigging_goto_weight_paint", text="Weight Paint", icon='TPAINT_HLT')

        row_scripts_2 = layout.row()
        row_scripts_2.operator("armature.amazing_rigging_ot_clean_transform", text="Clean Transform", icon='LOOP_BACK')
        row_scripts_2.operator("armature.collection_show_all", text="Export to UE", icon='EXPORT')

        layout.separator()

        layout.label(text="Bone Collections", icon='GROUP_BONE')
        row_ctrl = layout.row()
        row_ctrl.operator("armature.collection_show_all", text="Show All", icon='RESTRICT_VIEW_OFF')
        row_ctrl.operator("armature.collection_hide_all", text="Hide All", icon='RESTRICT_VIEW_ON')

        layout.separator()

        # Draw collections by split rules
        self.draw_split_bones_collections(layout, arm_data, target_armature)

    def draw_split_bones_collections(self, layout, arm_data, target_armature):
        """Draw bone collections from amazing_grid_data grouped by split rules"""
        global _ui_panel_rule_hidden, _ui_panel_pocket_hidden
        
        grid_data = getattr(arm_data, "amazing_grid_data", [])
        pockets = getattr(arm_data, "amazing_bone_pockets", [])
        b_cols = getattr(arm_data, "collections", None)

        if not grid_data or len(grid_data) == 0:
            return

        # Draw each rule's collections
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            rule_key = f"{arm_data.name}_{rule_idx}"
            is_hidden = _ui_panel_rule_hidden.get(rule_key, False)

            # Filter items for this rule
            rule_items = [item for item in grid_data if item.rule_index == rule_idx]
            
            if not rule_items:
                continue

            # Rule box - outer container
            rule_box = layout.box()
            
            # Rule header with fold button
            row_header = rule_box.row()
            icon_type = 'TRIA_RIGHT' if is_hidden else 'TRIA_DOWN'

            toggle_op = row_header.operator("armature.amazing_rigging_toggle_ui_panel_rule", text=f"{rule.name} ({len(rule_items)})", icon=icon_type, emboss=False)
            toggle_op.rule_index = rule_idx

            # Rule content (when expanded)
            if not is_hidden:
                # Filter pockets for this rule (by row AND rule_index)
                rule_rows = {item.row for item in rule_items}
                rule_pockets = [p for p in pockets if p.row in rule_rows and p.rule_index == rule_idx]
                pocket_rows = {p.row for p in rule_pockets}

                # Sort items by row/col
                sorted_items = sorted(rule_items, key=lambda x: (x.row, x.col))
                rows_dict = {}
                for item in sorted_items:
                    if item.row not in rows_dict:
                        rows_dict[item.row] = []
                    rows_dict[item.row].append(item)

                sorted_pocket_rows = sorted(pocket_rows)

                # Helper function to find which pocket affects a row
                def get_pocket_for_row(row_idx):
                    for i, pocket_row in enumerate(sorted_pocket_rows):
                        if pocket_row == row_idx:
                            for pocket in rule_pockets:
                                if pocket.row == pocket_row:
                                    return pocket
                        elif pocket_row < row_idx:
                            next_pocket_row = sorted_pocket_rows[i + 1] if i + 1 < len(sorted_pocket_rows) else None
                            if next_pocket_row is None or row_idx < next_pocket_row:
                                for pocket in rule_pockets:
                                    if pocket.row == pocket_row:
                                        return pocket
                    return None

                def is_pocket_hidden(pocket):
                    if pocket is None:
                        return False
                    pocket_key = f"{arm_data.name}_{rule_idx}_{pocket.row}"
                    return _ui_panel_pocket_hidden.get(pocket_key, False)

                # Group items by pocket or no-pocket
                pocket_items_dict = {}
                for pocket in rule_pockets:
                    pocket_items_dict[pocket.row] = []
                no_pocket_items = []
                
                for row_idx in sorted(rows_dict.keys()):
                    pocket = get_pocket_for_row(row_idx)
                    if pocket:
                        if pocket.row not in pocket_items_dict:
                            pocket_items_dict[pocket.row] = []
                        pocket_items_dict[pocket.row].extend(rows_dict[row_idx])
                    else:
                        no_pocket_items.extend(rows_dict[row_idx])

                # Draw pockets first (each pocket wraps its items)
                for pocket_row in sorted_pocket_rows:
                    pocket = None
                    for p in rule_pockets:
                        if p.row == pocket_row:
                            pocket = p
                            break
                    
                    if not pocket:
                        continue
                    
                    # Pocket box
                    pocket_box = rule_box.box()
                    pocket_header = pocket_box.row()
                    
                    # Use independent fold state per rule
                    pocket_key = f"{arm_data.name}_{rule_idx}_{pocket_row}"
                    is_pocket_hidden = _ui_panel_pocket_hidden.get(pocket_key, False)
                    icon_type_pocket = 'TRIA_RIGHT' if is_pocket_hidden else 'TRIA_DOWN'
                    
                    toggle_pocket_op = pocket_header.operator("armature.amazing_rigging_toggle_ui_panel_pocket", text=pocket.name, icon=icon_type_pocket, emboss=False)
                    toggle_pocket_op.pocket_row = pocket_row
                    toggle_pocket_op.rule_index = rule_idx
                    
                    # Pocket content (when expanded)
                    if not is_pocket_hidden:
                        pocket_items = pocket_items_dict.get(pocket_row, [])
                        if pocket_items:
                            # Group by row
                            pocket_rows_dict = {}
                            for item in pocket_items:
                                if item.row not in pocket_rows_dict:
                                    pocket_rows_dict[item.row] = []
                                pocket_rows_dict[item.row].append(item)
                            
                            # Draw items row by row
                            for item_row in sorted(pocket_rows_dict.keys()):
                                row_items = pocket_rows_dict[item_row]
                                if row_items:
                                    row_flow = pocket_box.row(align=True)
                                    for item in row_items:
                                        if item.is_hidden:
                                            continue
                                        
                                        if b_cols and item.name in b_cols:
                                            b_col = b_cols[item.name]
                                            row_flow.prop(b_col, "is_visible", text=item.note, toggle=True)
                                        else:
                                            row_flow.label(text=item.note)

                # Draw items without pocket
                if no_pocket_items:
                    no_pocket_rows_dict = {}
                    for item in no_pocket_items:
                        if item.row not in no_pocket_rows_dict:
                            no_pocket_rows_dict[item.row] = []
                        no_pocket_rows_dict[item.row].append(item)
                    
                    for item_row in sorted(no_pocket_rows_dict.keys()):
                        row_items = no_pocket_rows_dict[item_row]
                        if row_items:
                            row_flow = rule_box.row(align=True)
                            for item in row_items:
                                if item.is_hidden:
                                    continue
                                
                                if b_cols and item.name in b_cols:
                                    b_col = b_cols[item.name]
                                    row_flow.prop(b_col, "is_visible", text=item.note, toggle=True)
                                else:
                                    row_flow.label(text=item.note)

classes = [
    AMAZING_RIGGING_OT_toggle_ui_panel_rule,
    AMAZING_RIGGING_OT_toggle_ui_panel_pocket,
    AMAZING_RIGGING_OT_toggle_bone_collection,
    AMAZING_RIGGING_OT_show_all,
    AMAZING_RIGGING_OT_hide_all,
    AMAZING_RIGGING_PT_main_sidebar,
]