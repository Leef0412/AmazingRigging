import bpy
from bpy.types import Panel, PropertyGroup, Operator
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty

# Independent fold state for Split Bones Rules panel
_split_rules_hidden = {}  # {armature_data_name_rule_idx: is_hidden}

# Independent fold state for Ctrl Bones UI Settings panel (Layer Editor)
_layer_editor_rules_hidden = {}  # {armature_data_name_rule_idx: is_hidden}

class AMAZING_RIGGING_StringItem(PropertyGroup):
    value: StringProperty(name="Value", default="")

class AMAZING_RIGGING_SplitRule(PropertyGroup):
    name: StringProperty(name="Rule Name", default="New Rule")
    is_hidden: BoolProperty(name="Hidden", default=False)
    prefixes: CollectionProperty(type=AMAZING_RIGGING_StringItem)
    exact_matches: CollectionProperty(type=AMAZING_RIGGING_StringItem)

class AMAZING_RIGGING_CollectionItem(PropertyGroup):
    name: StringProperty(name="Bone Name")
    row: IntProperty(name="Row", default=0)
    col: IntProperty(name="Col", default=0)
    note: StringProperty(name="Note", default="")
    is_hidden: BoolProperty(name="Hidden", default=False)
    rule_index: IntProperty(name="Rule Index", default=0)  # Which split rule this item belongs to

class AMAZING_RIGGING_Bone_Pocket(PropertyGroup):
    row: IntProperty(name="Row", default=0)
    rule_index: IntProperty(name="Rule Index", default=0)
    name: StringProperty(name="Pocket Name", default="Bone Pocket")
    is_hidden: BoolProperty(name="Hidden", default=False)

class AMAZING_RIGGING_ArmatureProperties(PropertyGroup):
    editing_item_key: StringProperty(name="Editing Item Key", default="")
    editing_pocket_key: StringProperty(name="Editing Pocket Key", default="")
    editing_split_rule_key: StringProperty(name="Editing Split Rule Key", default="")
    editing_string_key: StringProperty(name="Editing String Key", default="")

class AMAZING_RIGGING_OT_init_data(Operator):
    bl_idname = "armature.amazing_rigging_init"
    bl_label = "Initialize Grid Data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        b_cols = getattr(arm_data, "collections", None)
        if not b_cols or len(b_cols) == 0:
            self.report({'ERROR'}, "No Bone Collections found!")
            return {'CANCELLED'}

        obj = None
        for scene_obj in context.scene.objects:
            if scene_obj.type == 'ARMATURE' and scene_obj.data == arm_data:
                obj = scene_obj
                break

        if not obj:
            self.report({'ERROR'}, "Cannot find armature object in scene!")
            return {'CANCELLED'}

        bones = arm_data.bones
        if not bones:
            self.report({'ERROR'}, "No bones found in this armature!")
            return {'CANCELLED'}

        # Clear existing grid data and pockets
        arm_data.amazing_grid_data.clear()
        arm_data.amazing_deform_grid_data.clear()
        arm_data.amazing_bone_pockets.clear()

        # Initialize split rules if empty
        if len(arm_data.amazing_split_rules) == 0:
            rule1 = arm_data.amazing_split_rules.add()
            rule1.name = "Ctrl Bones"
            rule1.is_hidden = False
            prefix1 = rule1.prefixes.add()
            prefix1.value = "DEF-"
            exact1 = rule1.exact_matches.add()
            exact1.value = "Root"

        # Ensure "Other" rule exists (auto catch-all, not shown in config panel)
        other_rule = None
        for rule in arm_data.amazing_split_rules:
            if rule.name == "Other":
                other_rule = rule
                break
        
        if other_rule is None:
            other_rule = arm_data.amazing_split_rules.add()
            other_rule.name = "Other"
            other_rule.is_hidden = False
            # No prefixes or exact matches - it's a catch-all

        # Classify bone collections using split rules
        matched_collection_names = set()
        rule_collections = {}  # rule_idx -> list of collection names

        # First pass: match collections with rules that have prefixes/exact matches
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            rule_collections[rule_idx] = []

            has_prefixes = len(rule.prefixes) > 0 and any(p.value for p in rule.prefixes)
            has_exact = len(rule.exact_matches) > 0 and any(e.value for e in rule.exact_matches)

            if not has_prefixes and not has_exact:
                continue

            for b_col in b_cols:
                if b_col.name in matched_collection_names:
                    continue

                should_include = False

                for bone in b_col.bones:
                    bone_name = bone.name

                    for prefix_item in rule.prefixes:
                        if prefix_item.value and bone_name.startswith(prefix_item.value):
                            should_include = True
                            break

                    if not should_include:
                        for exact_item in rule.exact_matches:
                            if exact_item.value and bone_name == exact_item.value:
                                should_include = True
                                break

                    if should_include:
                        break

                if should_include:
                    rule_collections[rule_idx].append(b_col.name)
                    matched_collection_names.add(b_col.name)

        # Second pass: assign unmatched collections to catch-all rules
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            has_prefixes = len(rule.prefixes) > 0 and any(p.value for p in rule.prefixes)
            has_exact = len(rule.exact_matches) > 0 and any(e.value for e in rule.exact_matches)

            if not has_prefixes and not has_exact:
                for b_col in b_cols:
                    if b_col.name not in matched_collection_names:
                        rule_collections[rule_idx].append(b_col.name)
                        matched_collection_names.add(b_col.name)

        # Add ALL matched collections to amazing_grid_data with rule_index
        # Each rule gets its own section, each collection gets its own row by default
        for rule_idx in sorted(rule_collections.keys()):
            collections = rule_collections[rule_idx]
            
            if not collections:
                continue

            # Add each collection as a separate row within this rule's section
            for col_idx, col_name in enumerate(collections):
                item = arm_data.amazing_grid_data.add()
                item.name = col_name
                item.row = col_idx  # Each collection gets its own row by default
                item.col = 0
                item.note = col_name
                item.rule_index = rule_idx  # Mark which rule this item belongs to

        for area in context.screen.areas:
            area.tag_redraw()

        total_items = len(arm_data.amazing_grid_data)
        self.report({'INFO'}, f"Initialized {total_items} items across {len(arm_data.amazing_split_rules)} rules.")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_set_active_collection(Operator):
    bl_idname = "armature.amazing_rigging_set_active"
    bl_label = "Set Active Collection"
    bl_options = {'INTERNAL'}

    collection_name: StringProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        b_cols = getattr(arm_data, "collections", None)

        if b_cols and self.collection_name in b_cols:
            arm_data.collections.active_name = self.collection_name
        return {'FINISHED'}

class AMAZING_RIGGING_OT_cancel_edit(Operator):
    bl_idname = "armature.amazing_rigging_cancel_edit"
    bl_label = "Cancel Edit"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        print(f"\n[DEBUG] Cancel Edit:")
        print(f"  - Current editing_key: '{arm_data.amazing_props.editing_item_key}")
        print(f"  - Current editing_pocket_key: '{arm_data.amazing_props.editing_pocket_key}")

        arm_data.amazing_props.editing_item_key = ""
        arm_data.amazing_props.editing_pocket_key = ""

        print(f"  - Cleared editing_key and editing_pocket_key")

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)

class AMAZING_RIGGING_OT_edit_note(Operator):
    bl_idname = "armature.amazing_rigging_edit_note"
    bl_label = "Edit Note"
    bl_options = {'REGISTER', 'UNDO'}

    item_name: StringProperty()
    target_row: IntProperty()
    target_col: IntProperty()
    rule_index: IntProperty(default=0)
    original_note: StringProperty()

    def modal(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if event.type == 'ESC':
            # arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
            grid_data = getattr(arm_data, "amazing_grid_data", [])

            print(f"\n[DEBUG] Edit Note - ESC pressed:")
            print(f"  - target_row: {self.target_row}, target_col: {self.target_col}")
            print(f"  - Current editing_key: 'arm_data.amazing_props.editing_item_key'")

            for item in grid_data:
                if item.name == self.item_name and item.row == self.target_row and item.col == self.target_col:
                    item.note = self.original_note
                    break
            else:
                editing_key = arm_data.amazing_props.editing_item_key
                if editing_key:
                    parts = editing_key.split("_")
                    if len(parts) == 3:
                        current_rule = int(parts[0])
                        current_row = int(parts[1])
                        current_col = int(parts[2])
                        for item in grid_data:
                            if item.rule_index == current_rule and item.row == current_row and item.col == current_col:
                                item.note = self.original_note
                                break

            arm_data.amazing_props.editing_item_key = ""
            print(f"  - Cleared editing_key")

            context.window_manager.event_timer_remove(self._timer)
            return {'CANCELLED'}

        if event.type == 'RET' or event.type == 'NUMPAD_ENTER':
            print(f"\n[DEBUG] Edit Note - Enter pressed:")
            print(f"  - target_row: {self.target_row}, target_col: {self.target_col}")
            print(f"  - Current editing_key: '{arm_data.amazing_props.editing_item_key}'")
            # arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
            arm_data.amazing_props.editing_item_key = ""
            print(f"  - Cleared editing_key")
            context.window_manager.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}


    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        b_cols = getattr(arm_data, "collections", None)
        original_note_value = ""

        print(f"\n[DEBUG] Edit Note - Execute:")
        print(f"  - item_name: {self.item_name}")
        print(f"  - target_row: {self.target_row}, target_col: {self.target_col}")

        if arm_data.amazing_props.editing_pocket_key:
            print(f"  - Pocket editing active, canceling")
            arm_data.amazing_props.editing_pocket_key = ""

        if b_cols and self.item_name in b_cols:
            arm_data.collections.active_name = self.item_name

            for item in grid_data:
                if item.name == self.item_name and item.row == self.target_row and item.col == self.target_col:
                    arm_data.amazing_props.editing_item_key = f"{self.rule_index}_{item.row}_{item.col}"
                    original_note_value = item.note
                    print(f"  - Found item, set editing_key: '{arm_data.amazing_props.editing_item_key}'")
                    print(f"  - original_note: '{original_note_value}'")
                    break

        self.original_note = original_note_value
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        for area in context.screen.areas:
            area.tag_redraw()

        return {'RUNNING_MODAL'}

class AMAZING_RIGGING_OT_confirm_note(Operator):
    bl_idname = "armature.amazing_rigging_confirm_note"
    bl_label = "Confirm Note"
    bl_options = {'REGISTER', 'UNDO'}

    item_name: StringProperty()
    target_row: IntProperty()
    target_col: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        for item in grid_data:
            if item.name == self.item_name and item.row == self.target_row and item.col == self.target_col:
                if not item.note.strip():
                    item.note = item.name
                break

        arm_data.amazing_props.editing_item_key = ""

        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_col_left(Operator):
    bl_idname = "armature.amazing_rigging_move_col_left"
    bl_label = "Move Collection Left"
    bl_description = "Move the selected Collection to the left"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        editing_key = arm_data.amazing_props.editing_item_key
        if not editing_key:
            self.report({'WARNING'}, "No Collection selected!")
            return {'CANCELLED'}

        parts = editing_key.split("_")
        if len(parts) != 3:
            self.report({'WARNING'}, "Invalid Collection Key!")
            return {'CANCELLED'}

        current_rule = int(parts[0])
        current_row = int(parts[1])
        current_col = int(parts[2])

        row_items = [item for item in grid_data if item.rule_index == current_rule and item.row == current_row]
        row_items_sorted = sorted(row_items, key=lambda x: x.col)

        current_item = None
        current_index = -1
        for i, item in enumerate(row_items_sorted):
            if item.col == current_col:
                current_item = item
                current_index = i
                break

        if not current_item or current_index == -1:
            self.report({'WARNING'}, "Current Collection not found!")
            return {'CANCELLED'}

        if current_index == 0:
            self.report({'WARNING'}, "Already at the first position!")
            return {'CANCELLED'}

        swap_item = row_items_sorted[current_index - 1]
        current_col_val = current_item.col
        current_item.col = swap_item.col
        swap_item.col = current_col_val

        arm_data.amazing_props.editing_item_key = f"{current_rule}_{current_item.row}_{current_item.col}"
        self.report({'INFO'}, f"Moved '{current_item.note}' left!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_col_right(Operator):
    bl_idname = "armature.amazing_rigging_move_col_right"
    bl_label = "Move Collection Right"
    bl_description = "Move the selected Collection to the right"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        editing_key = arm_data.amazing_props.editing_item_key
        if not editing_key:
            self.report({'WARNING'}, "No Collection selected!")
            return {'CANCELLED'}

        parts = editing_key.split("_")
        if len(parts) != 3:
            self.report({'WARNING'}, "Invalid Collection Key!")
            return {'CANCELLED'}

        current_rule = int(parts[0])
        current_row = int(parts[1])
        current_col = int(parts[2])

        row_items = [item for item in grid_data if item.rule_index == current_rule and item.row == current_row]
        row_items_sorted = sorted(row_items, key=lambda x: x.col)

        current_item = None
        current_index = -1
        for i, item in enumerate(row_items_sorted):
            if item.col == current_col:
                current_item = item
                current_index = i
                break

        if not current_item or current_index == -1:
            self.report({'WARNING'}, "Current Collection not found!")
            return {'CANCELLED'}

        if current_index == len(row_items_sorted) - 1:
            self.report({'WARNING'}, "Already at the last position!")
            return {'CANCELLED'}

        swap_item = row_items_sorted[current_index + 1]
        current_col_val = current_item.col
        current_item.col = swap_item.col
        swap_item.col = current_col_val

        arm_data.amazing_props.editing_item_key = f"{current_rule}_{current_item.row}_{current_item.col}"
        self.report({'INFO'}, f"Moved '{current_item.note}' right!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_row_up(Operator):
    bl_idname = "armature.amazing_rigging_move_row_up"
    bl_label = "Move Row Up"
    bl_description = "Move this row up"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        # Only consider items from this rule
        rule_rows_dict = {}
        for item in grid_data:
            if item.rule_index == self.rule_index:
                if item.row not in rule_rows_dict:
                    rule_rows_dict[item.row] = []
                rule_rows_dict[item.row].append(item)

        sorted_rows = sorted(rule_rows_dict.keys())

        current_row_index = -1
        for i, row_idx in enumerate(sorted_rows):
            if row_idx == self.target_row:
                current_row_index = i
                break

        if current_row_index == -1:
            self.report({'WARNING'}, "Current row not found!")
            return {'CANCELLED'}

        if current_row_index == 0:
            self.report({'WARNING'}, "Already at the top row!")
            return {'CANCELLED'}

        prev_row = sorted_rows[current_row_index - 1]

        # Only swap rows for this rule
        for item in grid_data:
            if item.rule_index == self.rule_index:
                if item.row == self.target_row:
                    item.row = prev_row
                elif item.row == prev_row:
                    item.row = self.target_row

        # Pockets are NOT affected by row move (pockets are global)

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 3 and int(parts[0]) == self.rule_index and int(parts[1]) == self.target_row:
                arm_data.amazing_props.editing_item_key = f"{parts[0]}_{prev_row}_{parts[2]}"

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Moved row up!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_row_down(Operator):
    bl_idname = "armature.amazing_rigging_move_row_down"
    bl_label = "Move Row Down"
    bl_description = "Move this row down"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        # Only consider items from this rule
        rule_rows_dict = {}
        for item in grid_data:
            if item.rule_index == self.rule_index:
                if item.row not in rule_rows_dict:
                    rule_rows_dict[item.row] = []
                rule_rows_dict[item.row].append(item)

        sorted_rows = sorted(rule_rows_dict.keys())

        current_row_index = -1
        for i, row_idx in enumerate(sorted_rows):
            if row_idx == self.target_row:
                current_row_index = i
                break

        if current_row_index == -1:
            self.report({'WARNING'}, "Current row not found!")
            return {'CANCELLED'}

        if current_row_index == len(sorted_rows) - 1:
            self.report({'WARNING'}, "Already at the bottom row!")
            return {'CANCELLED'}

        next_row = sorted_rows[current_row_index + 1]

        # Only swap rows for this rule
        for item in grid_data:
            if item.rule_index == self.rule_index:
                if item.row == self.target_row:
                    item.row = next_row
                elif item.row == next_row:
                    item.row = self.target_row

        # Pockets are NOT affected by row move (pockets are global)

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 3 and int(parts[0]) == self.rule_index and int(parts[1]) == self.target_row:
                arm_data.amazing_props.editing_item_key = f"{parts[0]}_{next_row}_{parts[2]}"

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Moved row down!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_insert_row(Operator):
    bl_idname = "armature.amazing_rigging_insert_row"
    bl_label = "Insert Row"
    bl_description = "Insert an empty row at this row"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        print(f"\n[DEBUG] Insert Row BELOW row: {self.target_row}, rule_index: {self.rule_index}")
        print(f"  - Current grid_data count: {len(grid_data)}")
        print(f"  - Current editing_key: '{arm_data.amazing_props.editing_item_key}")

        # Move all rows > target_row down by 1 (insert below target_row)
        for item in grid_data:
            if item.rule_index == self.rule_index and item.row > self.target_row:
                item.row += 1

        # Create empty item(placeholder item) for this rule BELOW target_row
        placeholder = grid_data.add()
        placeholder.name = ""
        placeholder.row = self.target_row + 1  # Insert BELOW the target row
        placeholder.col = 0
        placeholder.note = ""
        placeholder.rule_index = self.rule_index
        print(f"  - Created placeholder item at row {self.target_row + 1} (below row {self.target_row}) for rule {self.rule_index}")

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 3 and parts[2] != "empty":
                rule_idx = int(parts[0])
                row = int(parts[1])
                col = int(parts[2])
                if rule_idx == self.rule_index and row > self.target_row:
                    new_row = row + 1
                    arm_data.amazing_props.editing_item_key = f"{rule_idx}_{new_row}_{col}"
                    print(f"  - Update editing_key: {editing_key} -> {arm_data.amazing_props.editing_item_key}")

        for area in context.screen.areas:
            area.tag_redraw()

        print(f"  - Inserted Done")
        self.report({'INFO'}, f"Inserted empty row below Row: {self.target_row}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_delete_row(Operator):
    bl_idname = "armature.amazing_rigging_ot_delete_row"
    bl_label = "Delete Row"
    bl_description = "Delete this row"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        print(f"\n[DEBUG] Delete Row: {self.target_row}, rule_index: {self.rule_index}")
        print(f"  - Current grid_data count: {len(grid_data)}")

        # Only remove items from this rule at this row
        items_to_remove = []
        for i, item in enumerate(grid_data):
            if item.rule_index == self.rule_index and item.row == self.target_row:
                items_to_remove.append(i)
                print(f"  - Tag delete item[{i}: {item.name}")

        if not items_to_remove:
            self.report({'WARNING'}, "Row is already empty!")
            return {'CANCELLED'}

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 3:
                rule_idx = int(parts[0])
                row = int(parts[1])
                col = int(parts[2])
                if rule_idx == self.rule_index and row == self.target_row:
                    print(f"  - editing_key at the deleted row, clear: '{editing_key}'")
                    arm_data.amazing_props.editing_item_key = ""
                elif rule_idx == self.rule_index and row > self.target_row:
                    new_row = row - 1
                    arm_data.amazing_props.editing_item_key = f"{rule_idx}_{new_row}_{col}"
                    print(f"  - Update editing_key: {editing_key} -> {arm_data.amazing_props.editing_item_key}")

        for index in reversed(items_to_remove):
            grid_data.remove(index)

        # Update rows for this rule only
        for item in grid_data:
            if item.rule_index == self.rule_index and item.row > self.target_row:
                item.row -= 1

        # Pockets are NOT affected by row delete (pockets are global)

        for area in context.screen.areas:
            area.tag_redraw()

        print(f"  - Deleted Done, 剩余: {len(grid_data)}")
        self.report({'INFO'}, f"Deleted Row {self.target_row}!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_insert_collection(Operator):
    bl_idname = "armature.amazing_rigging_insert"
    bl_label = "Insert Collection to Amazing Rigging UI"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def modal(self, context, event):
        if event.type == 'ESC':
            arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
            grid_data = getattr(arm_data, "amazing_grid_data", [])

            editing_key = arm_data.amazing_props.editing_item_key
            if editing_key:
                parts = editing_key.split("_")
                if len(parts) == 3:
                    rule_idx = int(parts[0])
                    row = int(parts[1])
                    col = int(parts[2])
                    for item in grid_data:
                        if item.rule_index == rule_idx and item.row == row and item.col == col:
                            arm_data.amazing_props.editing_item_key = ""
                            break

            context.window_manager.event_timer_remove(self._timer)

            for area in context.screen.areas:
                area.tag_redraw()
            return {'CANCELLED'}

        if event.type == 'RET' or event.type == 'NUMPAD_ENTER':
            arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
            grid_data = getattr(arm_data, "amazing_grid_data", [])

            editing_key = arm_data.amazing_props.editing_item_key
            if editing_key:
                parts = editing_key.split("_")
                if len(parts) == 3:
                    rule_idx = int(parts[0])
                    row = int(parts[1])
                    col = int(parts[2])
                    for item in grid_data:
                        if item.rule_index == rule_idx and item.row == row and item.col == col:
                            if not item.note.strip():
                                item.note = item.name
                            arm_data.amazing_props.editing_item_key = ""
                            break

            context.window_manager.event_timer_remove(self._timer)

            for area in context.screen.areas:
                area.tag_redraw()
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])
        b_cols = getattr(arm_data, "collections", None)

        if not b_cols:
            self.report({'WARNING'}, "No Bone Collections found!")
            return {'CANCELLED'}

        active_collection_name = arm_data.collections.active_name
        if not active_collection_name:
            self.report({'WARNING'}, "No active bone collection selected!")
            return {'CANCELLED'}

        editing_key = arm_data.amazing_props.editing_item_key
        old_item_index = -1
        old_item_row = -1
        old_item_note = ""
        old_item_rule_index = self.rule_index  # Default to current rule
        placeholder_index = -1

        print(f"\n'='*60")
        print(f"[INSERT COLLECTION] Starting operation")
        print(f"  - target_row: {self.target_row}, rule_index: {self.rule_index}")
        print(f"  - active_collection: {active_collection_name}")
        print(f"  - current editing_key: '{editing_key}")

        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 3:
                old_rule = int(parts[0])
                old_row = int(parts[1])
                old_col = int(parts[2])
                old_item_row = old_row
                old_item_rule_index = old_rule

                for i, item in enumerate(grid_data):
                    if item.rule_index == old_rule and item.row == old_row and item.col == old_col:
                        old_item_index = i
                        old_item_note = item.note
                        break

        # Check target row have any placeholder (for this rule only)
        for i, item in enumerate(grid_data):
            if item.rule_index == self.rule_index and item.row == self.target_row and item.name == "":
                placeholder_index = i
                print(f"  - Found placeholder at index {i}, will replace it")
                break

        max_col = -1
        for item in grid_data:
            if item.rule_index == self.rule_index and item.row == self.target_row and item.name != "":
                max_col = max(max_col, item.col)

        new_col = max_col + 1

        already_exists = False
        for item in grid_data:
            if item.rule_index == self.rule_index and item.name == active_collection_name and item.row == self.target_row:
                already_exists = True
                break

        if already_exists:
            self.report({'WARNING'}, f"Collection '{active_collection_name}' already exists in row {self.target_row}!")
            return {'CANCELLED'}

        # Print grid state before modification
        print(f"\n[BEFORE MODIFICATION] Grid State:")
        for i, item in enumerate(grid_data):
            print(f"  [{i}] rule={item.rule_index}, row={item.row}, col={item.col}, name='{item.name}'")

        # have placeholder then replace it
        if placeholder_index >= 0:
            print(f"\n[PATH A] Replacing placeholder with '{active_collection_name}")
            print(f"  - old_item_index={old_item_index}, old_item_row={old_item_row}")
            print(f"  - placeholder_index={placeholder_index}")

            placeholder_item = grid_data[placeholder_index]
            placeholder_original_row = placeholder_item.row
            placeholder_original_rule = placeholder_item.rule_index
            print(f"  - placeholder_item BEFORE replace: rule={placeholder_item.rule_index}, row={placeholder_item.row}, col={placeholder_item.col}, name='{placeholder_item.name}")
            print(f"  - placeholder_item id={id(placeholder_item)}")

            placeholder_item.name = active_collection_name
            placeholder_item.col = new_col
            placeholder_item.note = old_item_note if old_item_note else active_collection_name
            # Ensure rule_index is correct
            placeholder_item.rule_index = self.rule_index

            print(f"  - placeholder_item AFTER replace: rule={placeholder_item.rule_index}, row={placeholder_item.row}, col={placeholder_item.col}, name='{placeholder_item.name}")

            if old_item_index >= 0:
                grid_data.remove(old_item_index)

                print(f"  - Grid AFTER removing old item:")
                for i, item in enumerate(grid_data):
                    maker = " <-- placeholder" if id(item) == id(placeholder_item) else ""
                    print(f"  [{i}] rule={item.rule_index}, row={item.row}, col={item.col}, name='{item.name}'{maker}")

                # Check old_row have any item (for the OLD rule)
                old_row_remaining_items = [item for item in grid_data if item.rule_index == old_item_rule_index and item.row == old_item_row]
                need_delete_row = (len(old_row_remaining_items) == 0)

                if need_delete_row and old_item_row < placeholder_original_row and old_item_rule_index == placeholder_original_rule:
                    placeholder_new_row = placeholder_original_row - 1
                else:
                    placeholder_new_row = placeholder_original_row

                # Reindex ONLY for the affected rule
                self.reindex_rule_rows(arm_data, grid_data, self.rule_index)
                if old_item_rule_index != self.rule_index:
                    self.reindex_rule_rows(arm_data, grid_data, old_item_rule_index)
                
                print(f"  - Grid AFTER reindex_dict")
                for i, item in enumerate(grid_data):
                    maker = " <-- placeholder" if id(item) == id(placeholder_item) else ""
                    print(f"  [{i}] rule={item.rule_index}, row={item.row}, col={item.col}, name='{item.name}'{maker}")

                found_placeholder = False
                for item in grid_data:
                    if item.rule_index == self.rule_index and item.name == active_collection_name and item.row == placeholder_new_row and item.col == new_col:
                        arm_data.amazing_props.editing_item_key = f"{item.rule_index}_{item.row}_{item.col}"
                        print(f"  - placeholder_item AFTER reindex: rule_idx={item.rule_index}, row={item.row}, col={item.col}, name='{item.name}")
                        found_placeholder = True
                        break

                if not found_placeholder:
                    print(f"  - ERROR: Cannot find placeholder after reindex")
            else:
                print(f"  - No old row to remove")
                arm_data.amazing_props.editing_item_key = f"{placeholder_item.rule_index}_{placeholder_item.row}_{placeholder_item.col}"
                print(f"  - SET editing_key: '{arm_data.amazing_props.editing_item_key}'")
        else:
            print(f"\n[PATH B] No placeholder, creating new item")

            actual_target_row = self.target_row
            if old_item_index >= 0:
                grid_data.remove(old_item_index)
                old_row_remaining_items = [item for item in grid_data if item.rule_index == old_item_rule_index and item.row == old_item_row]
                need_delete_row = (len(old_row_remaining_items) == 0)

                if need_delete_row and old_item_row < self.target_row and old_item_rule_index == self.rule_index:
                    actual_target_row = self.target_row - 1

                # Reindex ONLY for the affected rule
                self.reindex_rule_rows(arm_data, grid_data, old_item_rule_index)

                print(f"  - Grid AFTER reindex_dict:")
                for i, item in enumerate(grid_data):
                    print(f"    [{i}] rule={item.rule_index}, row={item.row}, col={item.col}, name='{item.name}'")

            # 计算新行的 max_col（只针对当前 rule）
            max_col = -1
            for item in grid_data:
                if item.rule_index == self.rule_index and item.row == actual_target_row:
                    max_col = max(max_col, item.col)
            new_col = max_col + 1

            item = grid_data.add()
            item.name = active_collection_name
            item.row = actual_target_row
            item.col = new_col
            item.rule_index = self.rule_index  # Set the rule_index
            item.note = old_item_note if old_item_note else active_collection_name
            arm_data.amazing_props.editing_item_key = f"{item.rule_index}_{item.row}_{item.col}"
            print(f"  - Created new item: rule_idx={item.rule_index}, row={item.row}, col={item.col}, name='{item.name}'")
            print(f"  - SET editing_key: '{arm_data.amazing_props.editing_item_key}'")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Inserted '{active_collection_name}' at Row {self.target_row}, Col {new_col}!")
        return {'RUNNING_MODAL'}

    def reindex_rule_rows(self, arm_data, grid_data, rule_idx):
        """Reindex rows for a SPECIFIC rule only, not all rules"""
        # Get all items for this rule
        rule_items = [item for item in grid_data if item.rule_index == rule_idx]
        
        if not rule_items:
            return
        
        # Group by row
        rows_dict = {}
        for item in rule_items:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)
        
        # Sort rows and renumber them sequentially
        sorted_rows = sorted(rows_dict.keys())
        for new_row_idx, old_row_idx in enumerate(sorted_rows):
            # Sort items in this row by col
            row_items = sorted(rows_dict[old_row_idx], key=lambda x: x.col)
            for new_col_idx, item in enumerate(row_items):
                item.row = new_row_idx
                item.col = new_col_idx

class AMAZING_RIGGING_OT_add_bone_pocket(Operator):
    bl_idname = "armature.amazing_rigging_add_bone_pocket"
    bl_label = "Add Pocket"
    bl_description = "Pocket can collapse/Expand bones collection on Amazing Rigging UI"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row and pocket.rule_index == self.rule_index:
                self.report({'WARNING'}, "Bone Pocket already exists in this row!")
                return {'CANCELLED'}

        pocket = arm_data.amazing_bone_pockets.add()
        pocket.row = self.target_row
        pocket.rule_index = self.rule_index
        pocket.name = "Bone Pocket"

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Added Bone Pocket at Row {self.target_row}!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_remove_bone_pocket(Operator):
    bl_idname = "armature.amazing_rigging_remove_bone_pocket"
    bl_label = "Remove Pocket"
    bl_description = "Remove bone pocket from this row"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        items_to_remove = []
        for i, pocket in enumerate(arm_data.amazing_bone_pockets):
            if pocket.row == self.target_row and pocket.rule_index == self.rule_index:
                items_to_remove.append(i)
                break

        if not items_to_remove:
            self.report({'WARNING'}, "Bone Pocket not found!")
            return {'CANCELLED'}

        for index in reversed(items_to_remove):
            arm_data.amazing_bone_pockets.remove(index)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, "Bone Pocket removed!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_edit_bone_pocket(Operator):
    bl_idname = "armature.amazing_rigging_edit_bone_pocket"
    bl_label = "Edit Pocket"
    bl_description = "Edit bone pocket name"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()
    rule_index: IntProperty(default=0)
    original_name: StringProperty()

    def modal(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if event.type == 'ESC':
            print(f"\n[DEBUG] Edit Bone Pocket - ESC pressed:")
            print(f"  - target_row: {self.target_row}")
            print(f"  - rule_index: {self.rule_index}")
            print(f"  - Current editing_pocket_key: '{arm_data.amazing_props.editing_pocket_key}'")

            for pocket in arm_data.amazing_bone_pockets:
                if pocket.row == self.target_row and pocket.rule_index == self.rule_index:
                    pocket.name = self.original_name
                    break

            arm_data.amazing_props.editing_pocket_key = ""
            print(f"  - Cleared editing_pocket_key")

            context.window_manager.event_timer_remove(self._timer)

            for area in context.screen.areas:
                area.tag_redraw()

            return {'CANCELLED'}

        if event.type == 'RET' or event.type == 'NUMPAD_ENTER':
            print(f"\n[DEBUG] Edit Bone Pocket - Enter pressed:")
            print(f"  - target_row: {self.target_row}")
            print(f"  - rule_index: {self.rule_index}")
            print(f"  - Current editing_pocket_key: '{arm_data.amazing_props.editing_pocket_key}'")

            arm_data.amazing_props.editing_pocket_key = ""
            print(f"  - Cleared editing_pocket_key")

            context.window_manager.event_timer_remove(self._timer)

            for area in context.screen.areas:
                area.tag_redraw()

            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        print(f"\n[DEBUG] Edit Bone Pocket - Invoke:")
        print(f"  - target_row: {self.target_row}")
        print(f"  - rule_index: {self.rule_index}")

        if arm_data.amazing_props.editing_item_key:
            print(f"  - Item editing active, canceling and restoring note")
            editing_key = arm_data.amazing_props.editing_item_key
            parts = editing_key.split("_")
            if len(parts) == 3:
                rule_idx = int(parts[0])
                row = int(parts[1])
                col = int(parts[2])
                grid_data = getattr(arm_data, "amazing_grid_data", [])
                for item in grid_data:
                    if item.rule_index == rule_idx and item.row == row and item.col == col:
                        if item.note != item.name:
                            item.note = item.name
                            print(f"  - Restored item note to: '{item.name}")
                        break
            arm_data.amazing_props.editing_item_key = ""

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row and pocket.rule_index == self.rule_index:
                arm_data.amazing_props.editing_pocket_key = f"{self.rule_index}_{pocket.row}"
                self.original_name = pocket.name
                print(f"  - Found pocket, set editing_pocket_key: '{arm_data.amazing_props.editing_pocket_key}'")
                print(f"  - original_name: '{self.original_name}'")
                break

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        for area in context.screen.areas:
            area.tag_redraw()

        return {'RUNNING_MODAL'}

# class AMAZING_RIGGING_OT_toggle_bone_pocket(Operator):
#     bl_idname = "armature.amazing_rigging_toggle_bone_pocket"
#     bl_label = "Toggle Pocket Visibility"
#     bl_description = "Toggle visibility of bones in this bone pocket on Amazing Rigging Ui"
#     bl_options = {'REGISTER', 'UNDO'}
#
#     pocket_row: IntProperty(name="Pocket Row", default=-1)
#
#     def execute(self, context):
#         arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
#         pockets = getattr(arm_data, "amazing_bone_pockets")
#
#         for pocket in pockets:
#             if pocket.row == self.pocket_row:
#                 pocket.is_hidden = not pocket.is_hidden
#                 status = "hidden" if pocket.is_hidden else "shown"
#
#                 for area in context.screen.areas:
#                     area.tag_redraw()
#
#                 self.report({'INFO'}, f"Toggle Pocket Visibility: {status}")
#                 return {'FINISHED'}
#         self.report({'WARNING'}, "Bone pocket not found!")
#         return {'CANCELLED'}

class AMAZING_RIGGING_OT_remove_from_grid(Operator):
    bl_idname = "armature.amazing_rigging_remove"
    bl_label = "Remove from Grid"
    bl_options = {'REGISTER', 'UNDO'}

    item_name: StringProperty()
    target_row: IntProperty()
    target_col: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        items_to_remove = []
        for i, item in enumerate(grid_data):
            if item.name == self.item_name and item.row == self.target_row and item.col == self.target_col:
                items_to_remove.append(i)
                break
        if not items_to_remove:
            self.report({'WARNING'}, "Collection not found in grid!")
            return {'CANCELLED'}

        for index in reversed(items_to_remove):
            grid_data.remove(index)

        self.reindex_dict(arm_data, grid_data)

        if arm_data.amazing_props.editing_item_key:
            arm_data.amazing_props.editing_item_key = ""

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Removed '{self.item_name}' from grid!")
        return {'FINISHED'}


    def reindex_dict(self, arm_data, grid_data):
        rows_dict = {}
        for item in grid_data:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        sorted_rows = sorted(rows_dict.keys())

        old_to_new_row = {}
        for new_row_idx, old_row_idx in enumerate(sorted_rows):
            old_to_new_row[old_row_idx] = new_row_idx

            row_items = sorted(rows_dict[old_row_idx], key=lambda x: x.col)
            for new_col_idx, item in enumerate(row_items):
                item.row = new_row_idx
                item.col = new_col_idx

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row in old_to_new_row:
                pocket.row = old_to_new_row[pocket.row]

class AMAZING_RIGGING_OT_toggle_bone_pocket(Operator):
    bl_idname = "armature.amazing_rigging_toggle_bone_pocket"
    bl_label = "Toggle Bone Pocket Visibility"
    bl_description = "Toggle visibility of bones in this bone pocket on Amazing Rigging UI"
    bl_options = {'INTERNAL'}

    pocket_row: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        pockets = getattr(arm_data, "amazing_bone_pockets", [])

        for pocket in pockets:
            if pocket.row == self.pocket_row:
                pocket.is_hidden = not pocket.is_hidden

                for area in context.screen.areas:
                    area.tag_redraw()
                return {'FINISHED'}

        return {'CANCELLED'}

# ========== Split Bones Rules Operators ==========

class AMAZING_RIGGING_OT_init_split_rules(Operator):
    bl_idname = "armature.amazing_rigging_init_split_rules"
    bl_label = "Initialize Split Rules"
    bl_description = "Initialize default split rules"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        # Clear existing
        arm_data.amazing_split_rules.clear()

        # Add default rules
        rule1 = arm_data.amazing_split_rules.add()
        rule1.name = "Ctrl Bones"
        rule1.is_hidden = False
        prefix1 = rule1.prefixes.add()
        prefix1.value = "DEF-"
        exact1 = rule1.exact_matches.add()
        exact1.value = "Root"

        # Auto-create "Other" rule (catch-all for unmatched collections)
        rule_other = arm_data.amazing_split_rules.add()
        rule_other.name = "Other"
        rule_other.is_hidden = False

        print(f"[DEBUG] Initialized {len(arm_data.amazing_split_rules)} split rules")

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Initialized {len(arm_data.amazing_split_rules)} split rules")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_add_split_rule(Operator):
    bl_idname = "armature.amazing_rigging_add_split_rule"
    bl_label = "Add Split Rule"
    bl_description = "Add a new split rule for bone collections"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        rule = arm_data.amazing_split_rules.add()
        rule.name = "New Rule"
        rule.is_hidden = False

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Added split rule: {rule.name}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_remove_split_rule(Operator):
    bl_idname = "armature.amazing_rigging_remove_split_rule"
    bl_label = "Remove Split Rule"
    bl_description = "Remove this split rule"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        rule = arm_data.amazing_split_rules[self.rule_index]
        
        # Prevent removing "Other" rule
        if rule.name == "Other":
            self.report({'WARNING'}, "Cannot remove the 'Other' rule (auto catch-all)!")
            return {'CANCELLED'}

        if len(arm_data.amazing_split_rules) <= 1:
            self.report({'WARNING'}, "At least one split rule must remain!")
            return {'CANCELLED'}

        rule_name = rule.name
        arm_data.amazing_split_rules.remove(self.rule_index)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Removed split rule: {rule_name}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_toggle_split_rule(Operator):
    bl_idname = "armature.amazing_rigging_toggle_split_rule"
    bl_label = "Toggle Split Rule"
    bl_description = "Toggle split rule visibility"
    bl_options = {'INTERNAL'}

    rule_index: IntProperty()

    def execute(self, context):
        global _split_rules_hidden
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if self.rule_index >= len(arm_data.amazing_split_rules):
            return {'CANCELLED'}

        rule_key = f"{arm_data.name}_{self.rule_index}"
        current_hidden = _split_rules_hidden.get(rule_key, False)
        _split_rules_hidden[rule_key] = not current_hidden

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}

class AMAZING_RIGGING_OT_toggle_layer_editor_rule(Operator):
    bl_idname = "armature.amazing_rigging_toggle_layer_editor_rule"
    bl_label = "Toggle Layer Editor Rule"
    bl_description = "Toggle layer editor rule visibility"
    bl_options = {'INTERNAL'}

    rule_index: IntProperty()

    def execute(self, context):
        global _layer_editor_rules_hidden
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if self.rule_index >= len(arm_data.amazing_split_rules):
            return {'CANCELLED'}

        rule_key = f"{arm_data.name}_{self.rule_index}"
        current_hidden = _layer_editor_rules_hidden.get(rule_key, False)
        _layer_editor_rules_hidden[rule_key] = not current_hidden

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_split_rule_up(Operator):
    bl_idname = "armature.amazing_rigging_move_split_rule_up"
    bl_label = "Move Split Rule Up"
    bl_description = "Move this split rule up (including all its items)"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if self.rule_index <= 0:
            self.report({'WARNING'}, "Already at the top!")
            return {'CANCELLED'}

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        # Don't allow moving the "Other" rule
        rule = arm_data.amazing_split_rules[self.rule_index]
        if rule.name == "Other":
            self.report({'WARNING'}, "Cannot move the 'Other' rule!")
            return {'CANCELLED'}

        # Move the rule
        arm_data.amazing_split_rules.move(self.rule_index, self.rule_index - 1)

        # Update rule_index for all grid items
        old_idx = self.rule_index
        new_idx = self.rule_index - 1
        for item in arm_data.amazing_grid_data:
            if item.rule_index == old_idx:
                item.rule_index = new_idx
            elif item.rule_index == new_idx:
                item.rule_index = old_idx

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Moved rule from position {old_idx} to {new_idx}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_split_rule_down(Operator):
    bl_idname = "armature.amazing_rigging_move_split_rule_down"
    bl_label = "Move Split Rule Down"
    bl_description = "Move this split rule down (including all its items)"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if self.rule_index >= len(arm_data.amazing_split_rules) - 1:
            self.report({'WARNING'}, "Already at the bottom!")
            return {'CANCELLED'}

        # Don't allow moving the "Other" rule
        rule = arm_data.amazing_split_rules[self.rule_index]
        if rule.name == "Other":
            self.report({'WARNING'}, "Cannot move the 'Other' rule!")
            return {'CANCELLED'}
        
        # Also don't allow moving a rule below Other
        target_rule = arm_data.amazing_split_rules[self.rule_index + 1]
        if target_rule.name == "Other":
            self.report({'WARNING'}, "Cannot move below 'Other' rule!")
            return {'CANCELLED'}

        # Move the rule
        arm_data.amazing_split_rules.move(self.rule_index, self.rule_index + 1)

        # Update rule_index for all grid items
        old_idx = self.rule_index
        new_idx = self.rule_index + 1
        for item in arm_data.amazing_grid_data:
            if item.rule_index == old_idx:
                item.rule_index = new_idx
            elif item.rule_index == new_idx:
                item.rule_index = old_idx

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Moved rule from position {old_idx} to {new_idx}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_add_split_prefix(Operator):
    bl_idname = "armature.amazing_rigging_add_split_prefix"
    bl_label = "Add Prefix"
    bl_description = "Add a new prefix to this split rule"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        rule = arm_data.amazing_split_rules[self.rule_index]
        prefix_item = rule.prefixes.add()
        prefix_item.value = ""

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Added prefix to {rule.name}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_remove_split_prefix(Operator):
    bl_idname = "armature.amazing_rigging_remove_split_prefix"
    bl_label = "Remove Prefix"
    bl_description = "Remove this prefix"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()
    prefix_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        rule = arm_data.amazing_split_rules[self.rule_index]
        if self.prefix_index >= len(rule.prefixes):
            self.report({'WARNING'}, "Invalid prefix index!")
            return {'CANCELLED'}

        rule.prefixes.remove(self.prefix_index)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, "Removed prefix")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_add_split_exact(Operator):
    bl_idname = "armature.amazing_rigging_add_split_exact"
    bl_label = "Add Exact Match"
    bl_description = "Add a new exact match to this split rule"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        rule = arm_data.amazing_split_rules[self.rule_index]
        exact_item = rule.exact_matches.add()
        exact_item.value = ""

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Added exact match to {rule.name}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_remove_split_exact(Operator):
    bl_idname = "armature.amazing_rigging_remove_split_exact"
    bl_label = "Remove Exact Match"
    bl_description = "Remove this exact match"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()
    exact_index: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        rule = arm_data.amazing_split_rules[self.rule_index]
        if self.exact_index >= len(rule.exact_matches):
            self.report({'WARNING'}, "Invalid exact match index!")
            return {'CANCELLED'}

        rule.exact_matches.remove(self.exact_index)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, "Removed exact match")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_edit_split_rule_name(Operator):
    bl_idname = "armature.amazing_rigging_edit_split_rule_name"
    bl_label = "Edit Split Rule Name"
    bl_description = "Edit split rule name"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()

    def modal(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if event.type == 'ESC':
            props.editing_split_rule_key = ""
            context.window_manager.event_timer_remove(self._timer)
            return {'CANCELLED'}

        if event.type == 'RET' or event.type == 'NUMPAD_ENTER':
            props.editing_split_rule_key = ""
            context.window_manager.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        props.editing_split_rule_key = f"rule_name_{self.rule_index}"

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        for area in context.screen.areas:
            area.tag_redraw()

        return {'RUNNING_MODAL'}

class AMAZING_RIGGING_OT_edit_string_item(Operator):
    bl_idname = "armature.amazing_rigging_edit_string_item"
    bl_label = "Edit String Item"
    bl_description = "Edit prefix or exact match value"
    bl_options = {'REGISTER', 'UNDO'}

    rule_index: IntProperty()
    string_type: StringProperty()  # 'prefix' or 'exact'
    string_index: IntProperty()
    original_value: StringProperty()

    def modal(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if event.type == 'ESC':
            if self.rule_index < len(arm_data.amazing_split_rules):
                rule = arm_data.amazing_split_rules[self.rule_index]
                if self.string_type == 'prefix' and self.string_index < len(rule.prefixes):
                    rule.prefixes[self.string_index].value = self.original_value
                elif self.string_type == 'exact' and self.string_index < len(rule.exact_matches):
                    rule.exact_matches[self.string_index].value = self.original_value

            props.editing_string_key = ""
            context.window_manager.event_timer_remove(self._timer)
            return {'CANCELLED'}

        if event.type == 'RET' or event.type == 'NUMPAD_ENTER':
            props.editing_string_key = ""
            context.window_manager.event_timer_remove(self._timer)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        props = arm_data.amazing_props

        if self.rule_index >= len(arm_data.amazing_split_rules):
            self.report({'WARNING'}, "Invalid rule index!")
            return {'CANCELLED'}

        rule = arm_data.amazing_split_rules[self.rule_index]
        if self.string_type == 'prefix':
            if self.string_index >= len(rule.prefixes):
                self.report({'WARNING'}, "Invalid prefix index!")
                return {'CANCELLED'}
            self.original_value = rule.prefixes[self.string_index].value
        elif self.string_type == 'exact':
            if self.string_index >= len(rule.exact_matches):
                self.report({'WARNING'}, "Invalid exact match index!")
                return {'CANCELLED'}
            self.original_value = rule.exact_matches[self.string_index].value

        props.editing_string_key = f"{self.rule_index}_{self.string_type}_{self.string_index}"

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        for area in context.screen.areas:
            area.tag_redraw()

        return {'RUNNING_MODAL'}

class AMAZING_RIGGING_PT_split_bones_rules(Panel):
    bl_label = "Split Bones Rules"
    bl_idname = "DATA_PT_amazing_rigging_split_bones_rules"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_order = 0  # Ensure this panel appears first

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'ARMATURE'

    def draw(self, context):
        layout = self.layout
        arm_data = context.armature

        # Debug: Check if arm_data and amazing_split_rules exist
        if not arm_data:
            layout.label(text="No armature data!", icon='ERROR')
            return

        if not hasattr(arm_data, "amazing_split_rules"):
            layout.label(text="amazing_split_rules not registered!", icon='ERROR')
            layout.label(text="Please restart Blender!", icon='ERROR')
            return

        props = arm_data.amazing_props

        # Debug info
        row_debug = layout.row()
        row_debug.label(text=f"Split rules count: {len(arm_data.amazing_split_rules)}", icon='INFO')

        # Draw each rule (EXCEPT "Other" which is auto-managed)
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            # Skip "Other" rule (it's auto-managed, not shown in config panel)
            if rule.name == "Other":
                continue

            rule_box = layout.box()

            # Use independent fold state per panel
            rule_key = f"{arm_data.name}_{rule_idx}"
            is_hidden = _split_rules_hidden.get(rule_key, False)

            # Rule header
            row_header = rule_box.row()
            icon_type = 'TRIA_DOWN' if not is_hidden else 'TRIA_RIGHT'

            # Editable rule name
            editing_key = f"rule_name_{rule_idx}"
            is_editing_name = props.editing_split_rule_key == editing_key

            if is_editing_name:
                row_header.prop(rule, "name", text="")
            else:
                toggle_op = row_header.operator("armature.amazing_rigging_toggle_split_rule", text=rule.name, icon=icon_type, emboss=False)
                toggle_op.rule_index = rule_idx

                # Edit name button
                edit_name_op = row_header.operator("armature.amazing_rigging_edit_split_rule_name", text="", icon='GREASEPENCIL')
                edit_name_op.rule_index = rule_idx

            # Move/Delete buttons
            if not is_hidden:
                move_row = row_header.row(align=True)
                move_up = move_row.operator("armature.amazing_rigging_move_split_rule_up", text="", icon='TRIA_UP')
                move_up.rule_index = rule_idx
                move_down = move_row.operator("armature.amazing_rigging_move_split_rule_down", text="", icon='TRIA_DOWN')
                move_down.rule_index = rule_idx

            remove_op = row_header.operator("armature.amazing_rigging_remove_split_rule", text="", icon='X')
            remove_op.rule_index = rule_idx

            # Rule content (when expanded)
            if not is_hidden:
                content_box = rule_box.box()

                # Prefix section
                content_box.label(text="Prefix:")
                for prefix_idx, prefix_item in enumerate(rule.prefixes):
                    prefix_row = content_box.row(align=True)

                    editing_key = f"{rule_idx}_prefix_{prefix_idx}"
                    is_editing = props.editing_string_key == editing_key

                    if is_editing:
                        prefix_row.prop(prefix_item, "value", text="")
                    else:
                        prefix_row.label(text=prefix_item.value if prefix_item.value else "(empty)")
                        edit_op = prefix_row.operator("armature.amazing_rigging_edit_string_item", text="", icon='GREASEPENCIL')
                        edit_op.rule_index = rule_idx
                        edit_op.string_type = 'prefix'
                        edit_op.string_index = prefix_idx

                    remove_prefix_op = prefix_row.operator("armature.amazing_rigging_remove_split_prefix", text="", icon='X')
                    remove_prefix_op.rule_index = rule_idx
                    remove_prefix_op.prefix_index = prefix_idx

                add_prefix_op = content_box.operator("armature.amazing_rigging_add_split_prefix", text="+ Add Prefix", icon='ADD')
                add_prefix_op.rule_index = rule_idx

                # Spacer
                content_box.separator()

                # Exact Match section
                content_box.label(text="Exact Match:")
                for exact_idx, exact_item in enumerate(rule.exact_matches):
                    exact_row = content_box.row(align=True)

                    editing_key = f"{rule_idx}_exact_{exact_idx}"
                    is_editing = props.editing_string_key == editing_key

                    if is_editing:
                        exact_row.prop(exact_item, "value", text="")
                    else:
                        exact_row.label(text=exact_item.value if exact_item.value else "(empty)")
                        edit_op = exact_row.operator("armature.amazing_rigging_edit_string_item", text="", icon='GREASEPENCIL')
                        edit_op.rule_index = rule_idx
                        edit_op.string_type = 'exact'
                        edit_op.string_index = exact_idx

                    remove_exact_op = exact_row.operator("armature.amazing_rigging_remove_split_exact", text="", icon='X')
                    remove_exact_op.rule_index = rule_idx
                    remove_exact_op.exact_index = exact_idx

                add_exact_op = content_box.operator("armature.amazing_rigging_add_split_exact", text="+ Add Exact Match", icon='ADD')
                add_exact_op.rule_index = rule_idx

        # Add new rule button
        layout.operator("armature.amazing_rigging_add_split_rule", text="+ Add Split Rule", icon='ADD')
        layout.separator()
        layout.operator("armature.amazing_rigging_init", text="Init Amazing Rigging UI", icon='FILE_REFRESH')

class AMAZING_RIGGING_PT_layer_editor(Panel):
    bl_label = "Amazing Rigging UI Settings"
    bl_idname = "DATA_PT_amazing_rigging_ui_settings"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'ARMATURE'

    def draw_split_bones_rules(self, layout, arm_data):
        """Draw Split Bones Rules section"""
        props = arm_data.amazing_props

        # Header
        box = layout.box()
        box.label(text="Split Bones Rules", icon='SETTINGS')

        # Draw each rule (skip "Other" rule - it's auto-managed)
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            rule_box = box.box()

            # Rule header
            row_header = rule_box.row()
            icon_type = 'TRIA_DOWN' if not rule.is_hidden else 'TRIA_RIGHT'

            toggle_op = row_header.operator("armature.amazing_rigging_toggle_split_rule", text=rule.name, icon=icon_type, emboss=False)
            toggle_op.rule_index = rule_idx

            # Edit/Move/Delete buttons
            if not rule.is_hidden:
                move_row = row_header.row(align=True)
                move_up = move_row.operator("armature.amazing_rigging_move_split_rule_up", text="", icon='TRIA_UP')
                move_up.rule_index = rule_idx
                move_down = move_row.operator("armature.amazing_rigging_move_split_rule_down", text="", icon='TRIA_DOWN')
                move_down.rule_index = rule_idx

            remove_op = row_header.operator("armature.amazing_rigging_remove_split_rule", text="", icon='X')
            remove_op.rule_index = rule_idx

            # Rule content (when expanded)
            if not rule.is_hidden:
                content_box = rule_box.box()

                # Prefix section
                content_box.label(text="Prefix:")
                for prefix_idx, prefix_item in enumerate(rule.prefixes):
                    prefix_row = content_box.row(align=True)

                    editing_key = f"{rule_idx}_prefix_{prefix_idx}"
                    is_editing = props.editing_string_key == editing_key

                    if is_editing:
                        prefix_row.prop(prefix_item, "value", text="")
                    else:
                        prefix_row.label(text=prefix_item.value if prefix_item.value else "(empty)")
                        edit_op = prefix_row.operator("armature.amazing_rigging_edit_string_item", text="", icon='GREASEPENCIL')
                        edit_op.rule_index = rule_idx
                        edit_op.string_type = 'prefix'
                        edit_op.string_index = prefix_idx

                    remove_prefix_op = prefix_row.operator("armature.amazing_rigging_remove_split_prefix", text="", icon='X')
                    remove_prefix_op.rule_index = rule_idx
                    remove_prefix_op.prefix_index = prefix_idx

                add_prefix_op = content_box.operator("armature.amazing_rigging_add_split_prefix", text="+ Add Prefix", icon='ADD')
                add_prefix_op.rule_index = rule_idx

                # Spacer
                content_box.separator()

                # Exact Match section
                content_box.label(text="Exact Match:")
                for exact_idx, exact_item in enumerate(rule.exact_matches):
                    exact_row = content_box.row(align=True)

                    editing_key = f"{rule_idx}_exact_{exact_idx}"
                    is_editing = props.editing_string_key == editing_key

                    if is_editing:
                        exact_row.prop(exact_item, "value", text="")
                    else:
                        exact_row.label(text=exact_item.value if exact_item.value else "(empty)")
                        edit_op = exact_row.operator("armature.amazing_rigging_edit_string_item", text="", icon='GREASEPENCIL')
                        edit_op.rule_index = rule_idx
                        edit_op.string_type = 'exact'
                        edit_op.string_index = exact_idx

                    remove_exact_op = exact_row.operator("armature.amazing_rigging_remove_split_exact", text="", icon='X')
                    remove_exact_op.rule_index = rule_idx
                    remove_exact_op.exact_index = exact_idx

                add_exact_op = content_box.operator("armature.amazing_rigging_add_split_exact", text="+ Add Exact Match", icon='ADD')
                add_exact_op.rule_index = rule_idx

        # Add new rule button
        box.operator("armature.amazing_rigging_add_split_rule", text="+ Add Split Rule", icon='ADD')

    def draw(self, context):
        layout = self.layout
        arm_data = context.armature

        layout.operator("armature.amazing_rigging_init", icon='FILE_REFRESH')
        layout.separator()

        grid_data = getattr(arm_data, "amazing_grid_data", [])
        pockets = getattr(arm_data, "amazing_bone_pockets", [])

        if len(grid_data) == 0:
            layout.label(text="Please initialize data first", icon='INFO')
            return

        # Draw each rule's data
        for rule_idx, rule in enumerate(arm_data.amazing_split_rules):
            # Filter items for this rule
            rule_items = [item for item in grid_data if item.rule_index == rule_idx]
            
            if not rule_items:
                continue

            # Rule header with fold button
            rule_box = layout.box()
            rule_header = rule_box.row()
            
            # Use independent fold state for layer editor
            rule_key = f"{arm_data.name}_{rule_idx}"
            is_hidden = _layer_editor_rules_hidden.get(rule_key, False)
            icon_type = 'TRIA_RIGHT' if is_hidden else 'TRIA_DOWN'
            
            # Toggle button
            toggle_op = rule_header.operator("armature.amazing_rigging_toggle_layer_editor_rule", text=f"{rule.name}", icon=icon_type, emboss=False)
            toggle_op.rule_index = rule_idx
            
            rule_header.label(text=f"({len(rule_items)} items)", icon='INFO')

            # Draw grid data for this rule (when expanded)
            if not is_hidden:
                # Filter pockets that apply to this rule's rows AND rule_index
                rule_rows = {item.row for item in rule_items}
                rule_pockets = [p for p in pockets if p.row in rule_rows and p.rule_index == rule_idx]
                pocket_rows = {p.row for p in rule_pockets}

                # Draw grid data for this rule inside rule box
                rule_content = rule_box.box()
                self.draw_rule_grid(rule_content, arm_data, rule_items, rule_pockets, pocket_rows, rule_idx)

    def draw_rule_grid(self, layout, arm_data, grid_data, pockets, pocket_rows, rule_idx):
        """Draw grid data for a single rule (same as old draw logic)"""
        props = arm_data.amazing_props
        editing_key = props.editing_item_key
        editing_pocket_key = props.editing_pocket_key

        sorted_items = sorted(grid_data, key=lambda x: (x.row, x.col))
        rows_dict = {}
        for item in sorted_items:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        existing_rows = sorted(rows_dict.keys())
        all_rows = set(existing_rows)
        
        if len(existing_rows) > 0:
            min_row = existing_rows[0]
            max_row = existing_rows[-1]
            for i in range(min_row, max_row + 1):
                all_rows.add(i)

        for pocket_row in pocket_rows:
            all_rows.add(pocket_row)

        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 3:
                editing_rule_idx = int(parts[0])
                editing_row = int(parts[1])
                if editing_rule_idx == rule_idx:
                    all_rows.add(editing_row)

        sorted_all_rows = sorted(all_rows)

        for row_idx in sorted_all_rows:
            row_items = rows_dict.get(row_idx, [])
            box = layout.box()

            is_row_active = False
            if editing_key:
                parts = editing_key.split("_")
                if len(parts) == 3:
                    active_rule_idx = int(parts[0])
                    active_row = int(parts[1])
                    if active_rule_idx == rule_idx:
                        is_row_active = (active_row == row_idx)

            row_header = box.row()
            row_header.label(text=f"{row_idx}")
            row_header.alignment = 'RIGHT'

            insert_op = row_header.operator("armature.amazing_rigging_insert", text="", icon='ADD')
            insert_op.target_row = row_idx
            insert_op.rule_index = rule_idx

            if row_idx not in pocket_rows:
                add_pocket_op = row_header.operator("armature.amazing_rigging_add_bone_pocket", text="", icon='COLLECTION_NEW')
                add_pocket_op.target_row = row_idx
                add_pocket_op.rule_index = rule_idx

            # Show col move buttons ONLY when editing AND row has > 1 items
            move_buttons_row = row_header.row()
            if is_row_active and len(row_items) > 1:
                move_buttons_row.operator("armature.amazing_rigging_move_col_left", text="", icon='TRIA_LEFT')
                move_buttons_row.operator("armature.amazing_rigging_move_col_right", text="", icon='TRIA_RIGHT')

            is_top_row = row_idx > 0
            row_up = row_header.row()
            row_up.enabled = is_top_row
            row_up_op = row_up.operator("armature.amazing_rigging_move_row_up", text="", icon="TRIA_UP")
            row_up_op.target_row = row_idx
            row_up_op.rule_index = rule_idx

            # Pocket display
            if row_idx in pocket_rows:
                pocket_col_flow = box.column_flow(align=True)
                pocket_box = pocket_col_flow.row()

                for pocket in pockets:
                    if pocket.row == row_idx and pocket.rule_index == rule_idx:
                        is_editing_pocket = (f"{rule_idx}_{pocket.row}" == editing_pocket_key)

                        if is_editing_pocket:
                            pocket_box.prop(pocket, "name", text="")
                        else:
                            edit_op = pocket_box.operator("armature.amazing_rigging_edit_bone_pocket", text=pocket.name, icon='COLLECTION_NEW')
                            edit_op.target_row = row_idx
                            edit_op.rule_index = rule_idx

                        pocket_remove_op = pocket_box.operator("armature.amazing_rigging_remove_bone_pocket", text="", icon='X')
                        pocket_remove_op.target_row = row_idx
                        pocket_remove_op.rule_index = rule_idx
                        break

            # Items display
            if len(row_items) > 0:
                col_flow = box.column_flow(columns=len(row_items), align=True)

                for item in row_items:
                    row_box = col_flow.box()
                    row = row_box.row(align=True)

                    item_key = f"{rule_idx}_{item.row}_{item.col}"
                    is_editing = props.editing_item_key == item_key
                    is_placeholder = (item.name == "")

                    if is_placeholder:
                        row.label(text="Empty Row", icon='DOT')
                    elif is_editing:
                        row.prop(item, "note", text="")
                    else:
                        edit_op = row.operator("armature.amazing_rigging_edit_note", text=item.note)
                        edit_op.item_name = item.name
                        edit_op.target_row = item.row
                        edit_op.target_col = item.col
                        edit_op.rule_index = rule_idx

                        remove_op = row.operator("armature.amazing_rigging_remove", text="", icon='X')
                        remove_op.item_name = item.name
                        remove_op.target_row = item.row
                        remove_op.target_col = item.col

            row_footer = box.row()
            row_footer.alignment = 'RIGHT'

            is_last_row = (row_idx > sorted_all_rows[-1] if sorted_all_rows else True)
            row_footer.enabled = not is_last_row
            insert_row_op = row_footer.operator("armature.amazing_rigging_insert_row", text="", icon='TRIA_DOWN_BAR')
            insert_row_op.target_row = row_idx
            insert_row_op.rule_index = rule_idx
            delete_row_op = row_footer.operator("armature.amazing_rigging_ot_delete_row", text="", icon='TRASH')
            delete_row_op.target_row = row_idx
            delete_row_op.rule_index = rule_idx
            row_down_op = row_footer.operator("armature.amazing_rigging_move_row_down", text="", icon='TRIA_DOWN')
            row_down_op.target_row = row_idx
            row_down_op.rule_index = rule_idx

classes = [
    AMAZING_RIGGING_StringItem,
    AMAZING_RIGGING_SplitRule,
    AMAZING_RIGGING_CollectionItem,
    AMAZING_RIGGING_Bone_Pocket,
    AMAZING_RIGGING_ArmatureProperties,
    AMAZING_RIGGING_OT_init_data,
    AMAZING_RIGGING_OT_set_active_collection,
    AMAZING_RIGGING_OT_cancel_edit,
    AMAZING_RIGGING_OT_edit_note,
    AMAZING_RIGGING_OT_confirm_note,
    AMAZING_RIGGING_OT_move_col_left,
    AMAZING_RIGGING_OT_move_col_right,
    AMAZING_RIGGING_OT_move_row_up,
    AMAZING_RIGGING_OT_move_row_down,
    AMAZING_RIGGING_OT_insert_row,
    AMAZING_RIGGING_OT_delete_row,
    AMAZING_RIGGING_OT_insert_collection,
    AMAZING_RIGGING_OT_add_bone_pocket,
    AMAZING_RIGGING_OT_remove_bone_pocket,
    AMAZING_RIGGING_OT_edit_bone_pocket,
    AMAZING_RIGGING_OT_remove_from_grid,
    AMAZING_RIGGING_OT_toggle_bone_pocket,
    AMAZING_RIGGING_OT_init_split_rules,
    AMAZING_RIGGING_OT_add_split_rule,
    AMAZING_RIGGING_OT_remove_split_rule,
    AMAZING_RIGGING_OT_toggle_split_rule,
    AMAZING_RIGGING_OT_toggle_layer_editor_rule,
    AMAZING_RIGGING_OT_move_split_rule_up,
    AMAZING_RIGGING_OT_move_split_rule_down,
    AMAZING_RIGGING_OT_add_split_prefix,
    AMAZING_RIGGING_OT_remove_split_prefix,
    AMAZING_RIGGING_OT_add_split_exact,
    AMAZING_RIGGING_OT_remove_split_exact,
    AMAZING_RIGGING_OT_edit_split_rule_name,
    AMAZING_RIGGING_OT_edit_string_item,
    AMAZING_RIGGING_PT_split_bones_rules,
    AMAZING_RIGGING_PT_layer_editor,
]