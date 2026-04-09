import bpy
from bpy.types import Panel, PropertyGroup, Operator
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty

class AMAZING_RIGGING_CollectionItem(PropertyGroup):
    name: StringProperty(name="Bone Name")
    row: IntProperty(name="Row", default=0)
    col: IntProperty(name="Col", default=0)
    note: StringProperty(name="Note", default="")
    is_hidden: BoolProperty(name="Hidden", default=False)

class AMAZING_RIGGING_Bone_Pocket(PropertyGroup):
    row: IntProperty(name="Row", default=0)
    name: StringProperty(name="Pocket Name", default="Bone Pocket")
    is_hidden: BoolProperty(name="Hidden", default=False)

class AMAZING_RIGGING_ArmatureProperties(PropertyGroup):
    editing_item_key: StringProperty(name="Editing Item Key", default="")
    editing_pocket_key: StringProperty(name="Editing Pocket Key", default="")

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

        arm_data.amazing_grid_data.clear()
        arm_data.amazing_deform_grid_data.clear()

        bones = arm_data.bones
        if not bones:
            self.report({'ERROR'}, "No bones found in this armature!")
            return {'CANCELLED'}

        for bone in bones:
            should_deform = bone.name.startswith('DEF-') or bone.name == 'Root'
            bone.use_deform = should_deform

        mixed_collections = []

        for b_col in b_cols:
            deform_bones = []
            control_bones = []

            for bone in b_col.bones:
                if bone.use_deform:
                    deform_bones.append(bone.name)
                else:
                    control_bones.append(bone.name)

            has_deform = len(deform_bones) > 0
            has_control = len(control_bones) > 0

            if has_deform:
                item = arm_data.amazing_deform_grid_data.add()
                item.name = b_col.name
                item.row = len(arm_data.amazing_deform_grid_data) - 1
                item.col = 0
                item.note = b_col.name

            if has_control:
                item = arm_data.amazing_grid_data.add()
                item.name = b_col.name
                item.row = len(arm_data.amazing_grid_data) - 1
                item.col = 0
                item.note = b_col.name

            if has_deform and has_control:
                mixed_collections.append(b_col.name)

        for area in context.screen.areas:
            area.tag_redraw()

        if mixed_collections:
            mixed_list = "\n".join(f"* {name}" for name in mixed_collections)
            self.report({'WARNING'}, f"Mixed Collections contain both deform and control bones:")

            def draw_message(self, context):
                self.layout.label(text="Warning: Mixed Bone Collections", icon='WARNING')
                self.layout.label(text="These collection contain both deform and control bones:")
                box = self.layout.box()
                for name in mixed_collections:
                    box.label(text=f"* {name}")
                self.layout.label(text="They have been added to both grid data.")

            context.window_manager.popup_menu(draw_message, title="Mixed Bone Collections Detected", icon='WARNING')

        total_items = len(arm_data.amazing_grid_data) + len(arm_data.amazing_deform_grid_data)
        self.report({'INFO'}, 'f"Initialized {total_items} ({len(arm_data.amazing_grid_data)} control, {len(arm_data.amazing_deform_grid_data)} deform).')
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
                    if len(parts) == 2:
                        current_row = int(parts[0])
                        current_col = int(parts[1])
                        for item in grid_data:
                            if item.row == current_row and item.col == current_col:
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
                    arm_data.amazing_props.editing_item_key = f"{item.row}_{item.col}"
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
        if len(parts) != 2:
            self.report({'WARNING'}, "Invalid Collection Key!")
            return {'CANCELLED'}

        current_row = int(parts[0])
        current_col = int(parts[1])

        row_items = [item for item in grid_data if item.row == current_row]
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

        arm_data.amazing_props.editing_item_key = f"{current_item.row}_{current_item.col}"
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
        if len(parts) != 2:
            self.report({'WARNING'}, "Invalid Collection Key!")
            return {'CANCELLED'}

        current_row = int(parts[0])
        current_col = int(parts[1])

        row_items = [item for item in grid_data if item.row == current_row]
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

        arm_data.amazing_props.editing_item_key = f"{current_item.row}_{current_item.col}"
        self.report({'INFO'}, f"Moved '{current_item.note}' right!")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_move_row_up(Operator):
    bl_idname = "armature.amazing_rigging_move_row_up"
    bl_label = "Move Row Up"
    bl_description = "Move this row up"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        rows_dict = {}
        for item in grid_data:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        sorted_rows = sorted(rows_dict.keys())

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

        for item in grid_data:
            if item.row == self.target_row:
                item.row = prev_row
            elif item.row == prev_row:
                item.row = self.target_row

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row:
                pocket.row = prev_row
            elif pocket.row == prev_row:
                pocket.row = self.target_row

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 2 and int(parts[0]) == self.target_row:
                arm_data.amazing_props.editing_item_key = f"{prev_row}_{parts[1]}"

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

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        rows_dict = {}
        for item in grid_data:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        sorted_rows = sorted(rows_dict.keys())

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

        for item in grid_data:
            if item.row == self.target_row:
                item.row = next_row
            elif item.row == next_row:
                item.row = self.target_row

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row:
                pocket.row = next_row
            elif pocket.row == next_row:
                pocket.row = self.target_row

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 2 and int(parts[0]) == self.target_row:
                arm_data.amazing_props.editing_item_key = f"{next_row}_{parts[1]}"

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

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        print(f"\n[DEBUG] Insert Row at: {self.target_row}")
        print(f"  - Current grid_data count: {len(grid_data)}")
        print(f"  - Current editing_key: '{arm_data.amazing_props.editing_item_key}")

        for item in grid_data:
            if item.row > self.target_row:
                item.row += 1

        # Create empty item(placeholder item)
        placeholder = grid_data.add()
        placeholder.name = ""
        placeholder.row = self.target_row + 1
        placeholder.col = 0
        placeholder.note = ""
        print(f"  - Created placeholder item at row ({self.target_row}")

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 2 and parts[1] != "empty":
                row = int(parts[0])
                col = int(parts[1])
                if row > self.target_row:
                    new_row = row + 1
                    arm_data.amazing_props.editing_item_key = f"{new_row}_{col}"
                    print(f"  - Update editing_key: {editing_key} -> {arm_data.amazing_props.editing_item_key}")

        for area in context.screen.areas:
            area.tag_redraw()

        print(f"  - Inserted Done")
        self.report({'INFO'}, f"Inserted empty row at Row: {self.target_row}")
        return {'FINISHED'}

class AMAZING_RIGGING_OT_delete_row(Operator):
    bl_idname = "armature.amazing_rigging_ot_delete_row"
    bl_label = "Delete Row"
    bl_description = "Delete this row"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
        grid_data = getattr(arm_data, "amazing_grid_data", [])

        print(f"\n[DEBUG] Delete Row: {self.target_row}")
        print(f"  - Current grid_data count: {len(grid_data)}")

        items_to_remove = []
        for i, item in enumerate(grid_data):
            if item.row == self.target_row:
                items_to_remove.append(i)
                print(f"  - Tag delete item[{i}: {item.name}")

        if not items_to_remove:
            self.report({'WARNING'}, "Row is already empty!")
            return {'CANCELLED'}

        editing_key = arm_data.amazing_props.editing_item_key
        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 2:
                row = int(parts[0])
                col = int(parts[1])
                if row == self.target_row:
                    print(f"  - editing_key at the deleted row, clear: '{editing_key}'")
                    arm_data.amazing_props.editing_item_key = ""
                elif row > self.target_row:
                    new_row = row - 1
                    arm_data.amazing_props.editing_item_key = f"{new_row}_{parts[1]}"
                    print(f"  - Update editing_key: {editing_key} -> {arm_data.amazing_props.editing_item_key}")

        for index in reversed(items_to_remove):
            grid_data.remove(index)

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row:
                pocket.row = -1

        for item in grid_data:
            if item.row > self.target_row:
                item.row -= 1

        pocket_to_remove = []
        for i, pocket in enumerate(arm_data.amazing_bone_pockets):
            if pocket.row == -1:
                pocket_to_remove.append(i)
            elif pocket.row > self.target_row:
                pocket.row -= 1

        for index in reversed(pocket_to_remove):
            arm_data.amazing_bone_pockets.remove(index)

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

    def modal(self, context, event):
        if event.type == 'ESC':
            arm_data = context.armature if hasattr(context, "armature") else context.active_object.data
            grid_data = getattr(arm_data, "amazing_grid_data", [])

            editing_key = arm_data.amazing_props.editing_item_key
            if editing_key:
                parts = editing_key.split("_")
                if len(parts) == 2:
                    row = int(parts[0])
                    col = int(parts[1])
                    for item in grid_data:
                        if item.row == row and item.col == col:
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
                if len(parts) == 2:
                    row = int(parts[0])
                    col = int(parts[1])
                    for item in grid_data:
                        if item.row == row and item.col == col:
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
        placeholder_index = -1

        print(f"\n'='*60")
        print(f"[INSERT COLLECTION] Starting operation")
        print(f"  - target_row: {self.target_row}")
        print(f"  - active_collection: {active_collection_name}")
        print(f"  - current editing_key: '{editing_key}")

        if editing_key:
            parts = editing_key.split("_")
            if len(parts) == 2:
                old_row = int(parts[0])
                old_col = int(parts[1])
                old_item_row = old_row

                for i, item in enumerate(grid_data):
                    if item.row == old_row and item.col == old_col:
                        old_item_index = i
                        old_item_note = item.note
                        break

        # Check target row have any placeholder
        for i, item in enumerate(grid_data):
            if item.row == self.target_row and item.name == "":
                placeholder_index = i
                print(f"  - Found placeholder at index {i}, will replace it")
                break

        max_col = -1
        for item in grid_data:
            if item.row == self.target_row and item.name != "":
                max_col = max(max_col, item.col)

        new_col = max_col + 1

        already_exists = False
        for item in grid_data:
            if item.name == active_collection_name and item.row == self.target_row:
                already_exists = True
                break

        if already_exists:
            self.report({'WARNING'}, f"Collection '{active_collection_name}' already exists in row {self.target_row}!")
            return {'CANCELLED'}

        # Print grid state before modification
        print(f"\n[BEFORE MODIFICATION] Grid State:")
        for i, item in enumerate(grid_data):
            print(f"  [{i}] row={item.row}, col={item.col}, name='{item.name}'")

        # have placeholder then replace it
        if placeholder_index >= 0:
            print(f"\n[PATH A] Replacing placeholder with '{active_collection_name}")
            print(f"  - old_item_index={old_item_index}, old_item_row={old_item_row}")
            print(f"  - placeholder_index={placeholder_index}")

            placeholder_item = grid_data[placeholder_index]
            placeholder_original_row = placeholder_item.row
            print(f"  - placeholder_item BEFORE replace: row={placeholder_item.row}, col={placeholder_item.col}, name='{placeholder_item.name}")
            print(f"  - placeholder_item id={id(placeholder_item)}")

            placeholder_item.name = active_collection_name
            placeholder_item.col = new_col
            placeholder_item.note = old_item_note if old_item_note else active_collection_name

            print(f"  - placeholder_item AFTER replace: row={placeholder_item.row}, col={placeholder_item.col}, name='{placeholder_item.name}")

            if old_item_index >= 0:
                grid_data.remove(old_item_index)

                print(f"  - Grid AFTER removing old item:")
                for i, item in enumerate(grid_data):
                    maker = " <-- placeholder" if id(item) == id(placeholder_item) else ""
                    print(f"  [{i}] row={item.row}, col={item.col}, name='{item.name}'{maker}")

                # Check old_row have any item
                old_row_remaining_items = [item for item in grid_data if item.row == old_item_row]
                need_delete_row = (len(old_row_remaining_items) == 0)

                if need_delete_row and old_item_row < placeholder_original_row:
                    placeholder_new_row = placeholder_original_row - 1
                else:
                    placeholder_new_row = placeholder_original_row

                # self.reindex_rows(arm_data, grid_data)
                self.reindex_dict(arm_data, grid_data)
                print(f"  - Grid AFTER reindex_dict")
                for i, item in enumerate(grid_data):
                    maker = " <-- placeholder" if id(item) == id(placeholder_item) else ""
                    print(f"  [{i}] row={item.row}, col={item.col}, name='{item.name}'{maker}")

                found_placeholder = False
                for item in grid_data:
                    if item.name == active_collection_name and item.row == placeholder_new_row and item.col == new_col:
                        arm_data.amazing_props.editing_item_key = f"{item.row}_{item.col}"
                        print(f"  - placeholder_item AFTER reindex: row={item.row}, col={item.col}, name='{item.name}")
                        found_placeholder = True
                        break

                if not found_placeholder:
                    print(f"  - ERROR: Cannot find placeholder after reindex")
            else:
                print(f"  - No old row to remove")
                arm_data.amazing_props.editing_item_key = f"{placeholder_item.row}_{placeholder_item.col}"
                print(f"  - SET editing_key: '{arm_data.amazing_props.editing_item_key}'")
        else:
            print(f"\n[PATH B] No placeholder, creating new item")

            actual_target_row = self.target_row
            if old_item_index >= 0:
                grid_data.remove(old_item_index)
                old_row_remaining_items = [item for item in grid_data if item.row == old_item_row]
                need_delete_row = (len(old_row_remaining_items) == 0)

                if need_delete_row and old_item_row < self.target_row:
                    actual_target_row = self.target_row - 1

                self.reindex_dict(arm_data, grid_data)

                print(f"  - Grid AFTER reindex_dict:")
                for i, item in enumerate(grid_data):
                    print(f"    [{i}] row={item.row}, col={item.col}, name='{item.name}'")

            # 计算新行的 max_col（排除 placeholder）
            max_col = -1
            for item in grid_data:
                if item.row == actual_target_row:
                    max_col = max(max_col, item.col)
            new_col = max_col + 1

            item = grid_data.add()
            item.name = active_collection_name
            item.row = actual_target_row
            item.col = new_col
            item.note = old_item_note if old_item_note else active_collection_name
            arm_data.amazing_props.editing_item_key = f"{item.row}_{item.col}"
            print(f"  - Created new item: row={item.row}, col={item.col}, name='{item.name}'")
            print(f"  - SET editing_key: '{arm_data.amazing_props.editing_item_key}'")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        for area in context.screen.areas:
            area.tag_redraw()

        self.report({'INFO'}, f"Inserted '{active_collection_name}' at Row {self.target_row}, Col {new_col}!")
        return {'RUNNING_MODAL'}

    def reindex_dict(self, arm_data, grid_data):
        # Rebuild all row and col , update editingkey
        rows_dict = {}
        for item in grid_data:
            if item.row not in rows_dict:
                rows_dict[item.row] = []
            rows_dict[item.row].append(item)

        sorted_rows = sorted(rows_dict.keys())

        # Remerber old row to new row mapping
        old_to_new_row = {}
        for new_row_idx, old_row_idx in enumerate(sorted_rows):
            old_to_new_row[old_row_idx] = new_row_idx

            # Sort all of item cols in this row
            row_items = sorted(rows_dict[old_row_idx], key=lambda x: x.col)
            for new_col_idx, item in enumerate(row_items):
                item.row = new_row_idx
                item.col = new_col_idx

        # Update Bone Collection
        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row in old_to_new_row:
                pocket.row = old_to_new_row[pocket.row]

class AMAZING_RIGGING_OT_add_bone_pocket(Operator):
    bl_idname = "armature.amazing_rigging_add_bone_pocket"
    bl_label = "Add Pocket"
    bl_description = "Pocket can collapse/Expand bones collection on Amazing Rigging UI"
    bl_options = {'REGISTER', 'UNDO'}

    target_row: IntProperty()

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row:
                self.report({'WARNING'}, "Bone Pocket already exists in this row!")
                return {'CANCELLED'}

        pocket = arm_data.amazing_bone_pockets.add()
        pocket.row = self.target_row
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

    def execute(self, context):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        items_to_remove = []
        for i, pocket in enumerate(arm_data.amazing_bone_pockets):
            if pocket.row == self.target_row:
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
    original_name: StringProperty()

    def modal(self, context, event):
        arm_data = context.armature if hasattr(context, "armature") else context.active_object.data

        if event.type == 'ESC':
            print(f"\n[DEBUG] Edit Bone Pocket - ESC pressed:")
            print(f"  - target_row: {self.target_row}")
            print(f"  - Current editing_pocket_key: '{arm_data.amazing_props.editing_pocket_key}'")

            for pocket in arm_data.amazing_bone_pockets:
                if pocket.row == self.target_row:
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

        if arm_data.amazing_props.editing_item_key:
            print(f"  - Item editing active, canceling and restoring note")
            editing_key = arm_data.amazing_props.editing_item_key
            parts = editing_key.split("_")
            if len(parts) == 2:
                row = int(parts[0])
                col = int(parts[1])
                grid_data = getattr(arm_data, "amazing_grid_data", [])
                for item in grid_data:
                    if item.row == row and item.col == col:
                        if item.note != item.name:
                            item.note = item.name
                            print(f"  - Restored item note to: '{item.name}")
                        break
            arm_data.amazing_props.editing_item_key = ""

        for pocket in arm_data.amazing_bone_pockets:
            if pocket.row == self.target_row:
                arm_data.amazing_props.editing_pocket_key = f"{pocket.row}"
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

class AMAZING_RIGGING_PT_layer_editor(Panel):
    bl_label = "Ctrl bones UI - Amazing Rigging"
    bl_idname = "DATA_PT_amazing_rigging_ui_settings"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'ARMATURE'

    def draw(self, context):
        layout = self.layout
        arm_data =context.armature

        layout.operator("armature.amazing_rigging_init", icon='FILE_REFRESH')
        layout.separator()

        grid_data = getattr(arm_data, "amazing_grid_data", [])
        pockets = getattr(arm_data, "amazing_bone_pockets", [])
        pocket_rows = {pocket.row for pocket in pockets}

        editing_key = arm_data.amazing_props.editing_item_key
        editing_pocket_key = arm_data.amazing_props.editing_pocket_key

        if editing_key:
            print(f"\n[DEBUG] Draw - Current editing_key: '{editing_key}'")

            parts = editing_key.split("_")
            if len(parts) == 2:
                row = int(parts[0])
                col = int(parts[1])

                item_exists = False
                for item in grid_data:
                    if item.row == row and item.col == col:
                        item_exists = True
                        break

                if not item_exists:
                    print(f"[DEBUG] Draw - Item {editing_key} not found, clearing editing_key")
                    # arm_data.amazing_props.editing_item_key = ""
                    editing_key = ""
                    # for area in context.screen.areas:
                    #     area.tag_redraw()
                    return

        pocket_editing_row = -1
        if editing_pocket_key:
            for pocket in pockets:
                if f"{pocket.row}" == editing_pocket_key:
                    pocket_editing_row = pocket.row
                    print(f"[DEBUG] Draw - Valid pocket editing: row={pocket_editing_row}")
                    break
            if pocket_editing_row == -1:
                print(f"[DEBUG] Draw - Invalid editing_pocket_key: '{editing_pocket_key}, ignoring")

        if len(grid_data) > 0:
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

            editing_key_row = -1
            if editing_key:
                parts = editing_key.split("_")
                if len(parts) == 2:
                    editing_row = int(parts[0])
                    all_rows.add(editing_row)
                    editing_key_row = editing_row

            sorted_all_rows = sorted(all_rows)
            total_rows = len(sorted_all_rows)

            for row_idx in sorted_all_rows:
                row_items = rows_dict.get(row_idx, [])
                box = layout.box()

                is_row_active = False
                if editing_key:
                    parts = editing_key.split("_")
                    if len(parts) == 2:
                        active_row = int(parts[0])
                        is_row_active = (active_row == row_idx)
                        if is_row_active:
                            print(f"[DEBUG] Draw - Row {row_idx} is active row")

                row_header = box.row()
                row_header.label(text=f"{row_idx}")
                row_header.alignment = 'RIGHT'

                insert_op = row_header.operator("armature.amazing_rigging_insert", text="", icon='ADD')
                insert_op.target_row = row_idx

                if row_idx not in pocket_rows:
                    add_pocket_op = row_header.operator("armature.amazing_rigging_add_bone_pocket", text="", icon='COLLECTION_NEW')
                    add_pocket_op.target_row = row_idx

                move_buttons_row = row_header.row()
                if is_row_active and len(row_items) > 1:
                    move_buttons_row.operator("armature.amazing_rigging_move_col_left", text="", icon='TRIA_LEFT')
                    move_buttons_row.operator("armature.amazing_rigging_move_col_right", text="", icon='TRIA_RIGHT')

                is_top_row = row_idx > 0
                row_up = row_header.row()
                row_up.enabled = is_top_row
                row_up_op = row_up.operator("armature.amazing_rigging_move_row_up", text="", icon="TRIA_UP")
                row_up_op.target_row = row_idx

                if row_idx in pocket_rows:
                    pocket_col_flow = box.column_flow(align=True)
                    pocket_box = pocket_col_flow.row()

                    for pocket in pockets:
                        if pocket.row == row_idx:
                            is_editing_pocket = (pocket_editing_row == pocket.row)

                            if is_editing_pocket:
                                print(f"[DEBUG] Draw - Showing edit box for pocket row={pocket.row}")
                                pocket_box.prop(pocket, "name", text="")
                            else:
                                edit_op = pocket_box.operator("armature.amazing_rigging_edit_bone_pocket", text=pocket.name, icon='COLLECTION_NEW')
                                edit_op.target_row = row_idx

                            pocket_remove_op = pocket_box.operator("armature.amazing_rigging_remove_bone_pocket", text="", icon='X')
                            pocket_remove_op.target_row = row_idx
                            break

                if len(row_items) > 0:
                    col_flow = box.column_flow(columns=len(row_items), align=True)

                    for item in row_items:
                        row_box = col_flow.box()
                        row = row_box.row(align=True)

                        item_key = f"{item.row}_{item.col}"
                        editing_key = f"{item.row}_{item.col}"
                        is_editing = arm_data.amazing_props.editing_item_key == editing_key
                        is_placeholder = (item.name == "")

                        if is_placeholder:
                            row.label(text="Empty Row", icon='DOT')
                        elif is_editing:
                            print(f"[DEBUG] Draw - Editing item: {editing_key}")
                            row.prop(item, "note", text="")
                        else:
                            edit_op = row.operator("armature.amazing_rigging_edit_note", text=item.note)
                            edit_op.item_name = item.name
                            edit_op.target_row = item.row
                            edit_op.target_col = item.col

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
                delete_row_op = row_footer.operator("armature.amazing_rigging_ot_delete_row", text="", icon='TRASH')
                delete_row_op.target_row = row_idx
                row_down_op = row_footer.operator("armature.amazing_rigging_move_row_down", text="", icon='TRIA_DOWN')
                row_down_op.target_row = row_idx

        else:
            layout.label(text="Please initialize data first", icon='INFO')

classes = [
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
    AMAZING_RIGGING_PT_layer_editor,
]