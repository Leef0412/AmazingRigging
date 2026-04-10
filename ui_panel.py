import bpy
from bpy.types import Panel, Operator
from bpy.props import StringProperty
from datetime import datetime

_last_pose_armature = None

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

        sorted_items = sorted(grid_data, key=lambda x: (x.row, x.col))

        rows_dict = {}
        for item in sorted_items:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        b_cols = getattr(arm_data, "collections", None)

        sorted_pocket_rows = sorted(pocket_rows)

        def get_pocket_for_row(row_idx):
            for i, pocket_row in enumerate(sorted_pocket_rows):
                if pocket_row == row_idx:
                    for pocket in pockets:
                        if pocket.row == pocket_row:
                            return pocket
                elif pocket_row < row_idx:
                    next_pocket_row = sorted_pocket_rows[i + 1] if i + 1 < len(sorted_pocket_rows) else None
                    if next_pocket_row is None or row_idx < next_pocket_row:
                        for pocket in pockets:
                            if pocket.row == pocket_row:
                                return pocket
            return None

        def is_pocket_hidden(pocket):
            if pocket is None:
                return False
            return pocket.is_hidden

        all_rows = sorted(set(list(rows_dict.keys()) + list(pocket_rows)))

        for row_idx in all_rows:
            if row_idx in pocket_rows:
                for pocket in pockets:
                    if pocket.row == row_idx:
                        pocket_row_ui = layout.row()
                        icon_type = 'TRIA_RIGHT' if pocket.is_hidden else 'TRIA_DOWN'

                        toggle_op = pocket_row_ui.operator("armature.amazing_rigging_toggle_bone_pocket", text=pocket.name, icon=icon_type, emboss=False)
                        toggle_op.pocket_row = pocket.row
                        pocket_row_ui.alignment = 'CENTER'
                        break

            pocket = get_pocket_for_row(row_idx)
            pocket_hidden = is_pocket_hidden(pocket)

            if pocket_hidden:
                continue

            if row_idx in rows_dict:
                row_items = rows_dict[row_idx]
                if len(row_items) > 0:
                    row_flow = layout.row(align=True)

                    for item in row_items:
                        if item.is_hidden:
                            continue

                        if b_cols and item.name in b_cols:
                            b_col = b_cols[item.name]
                            row_flow.prop(b_col, "is_visible", text=item.note, toggle=True)
                        else:
                            row_flow.label(text=item.note)

        # ========== Draw Split Bones Collections ==========
        self.draw_split_bones_collections(layout, arm_data, target_armature)

    def draw_split_bones_collections(self, layout, arm_data, target_armature):
        """Draw bone collections based on split rules"""
        props = arm_data.amazing_props

        # If no split rules, skip
        if len(arm_data.amazing_split_rules) == 0:
            return

        b_cols = getattr(arm_data, "collections", None)
        if not b_cols:
            return

        # Get all bones and classify them by split rules
        bones = arm_data.bones
        if not bones:
            return

        # Track which collections have been matched
        matched_collection_names = set()

        # First pass: match collections with rules that have prefixes/exact matches
        rule_matches = {}  # rule_idx -> list of collection names

        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            rule_matches[rule_idx] = []

            # Skip rules with no prefixes and no exact matches (they're "catch-all" rules)
            has_prefixes = len(rule.prefixes) > 0 and any(p.value for p in rule.prefixes)
            has_exact = len(rule.exact_matches) > 0 and any(e.value for e in rule.exact_matches)

            if not has_prefixes and not has_exact:
                continue

            for b_col in b_cols:
                # Skip if already matched
                if b_col.name in matched_collection_names:
                    continue

                # Check if any bone in this collection matches the rule
                should_include = False

                for bone in b_col.bones:
                    bone_name = bone.name

                    # Check prefixes
                    for prefix_item in rule.prefixes:
                        if prefix_item.value and bone_name.startswith(prefix_item.value):
                            should_include = True
                            break

                    # Check exact matches
                    if not should_include:
                        for exact_item in rule.exact_matches:
                            if exact_item.value and bone_name == exact_item.value:
                                should_include = True
                                break

                    if should_include:
                        break

                if should_include:
                    rule_matches[rule_idx].append(b_col.name)
                    matched_collection_names.add(b_col.name)

        # Second pass: assign unmatched collections to catch-all rules
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            has_prefixes = len(rule.prefixes) > 0 and any(p.value for p in rule.prefixes)
            has_exact = len(rule.exact_matches) > 0 and any(e.value for e in rule.exact_matches)

            if not has_prefixes and not has_exact:
                # This is a catch-all rule, add unmatched collections
                for b_col in b_cols:
                    if b_col.name not in matched_collection_names:
                        rule_matches[rule_idx].append(b_col.name)
                        matched_collection_names.add(b_col.name)

        # Draw each rule's collections
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            if rule.is_hidden:
                continue

            matched_collections = rule_matches.get(rule_idx, [])

            if matched_collections:
                row_label = layout.row()
                row_label.label(text=f"{rule.name}", icon='GROUP_BONE')

                row_flow = layout.row(align=True)
                for col_name in matched_collections:
                    if b_cols and col_name in b_cols:
                        b_col = b_cols[col_name]
                        row_flow.prop(b_col, "is_visible", text=col_name, toggle=True)
                    else:
                        row_flow.label(text=col_name)

                layout.separator()

classes = [
    AMAZING_RIGGING_OT_toggle_bone_collection,
    AMAZING_RIGGING_OT_show_all,
    AMAZING_RIGGING_OT_hide_all,
    AMAZING_RIGGING_PT_main_sidebar,
]