import bpy
from bpy.props import StringProperty

# It's good practice to import numpy where it's used, inside a try-except block
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------

def get_first_selected_other_than_active(context):
    """
    Finds the AssetRepresentation of the first selected asset that is not the active one.
    """
    active_asset_representation = context.asset
    for asset_representation in context.selected_assets:
        if asset_representation != active_asset_representation:
            return asset_representation
    return None

def show_message_box(message="", title="Message", icon='INFO'):
    """Helper function to display a popup message."""
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

# -----------------------------------------------------------------------------
# OPERATORS
# -----------------------------------------------------------------------------

class ASSET_OT_copy_selected_to_active(bpy.types.Operator):
    """Copies the thumbnail from a selected asset to the active (last selected) asset"""
    bl_idname = "asset.copy_thumbnail_selected_to_active"
    bl_label = "Copy Selected to Active"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area.ui_type == 'ASSETS'

    def execute(self, context):
        if not hasattr(context, 'selected_assets') or len(context.selected_assets) <= 1:
            self.report({'WARNING'}, "Please select at least two assets (source, then target).")
            return {'CANCELLED'}

        target_asset_repr = context.asset
        source_asset_repr = get_first_selected_other_than_active(context)

        if not source_asset_repr:
            self.report({'WARNING'}, "Could not find a source asset (select source, then shift+select target).")
            return {'CANCELLED'}
        if not target_asset_repr:
            self.report({'WARNING'}, "Could not find a target asset (the last selected one).")
            return {'CANCELLED'}
            
        source_asset = source_asset_repr.local_id
        target_asset = target_asset_repr.local_id
        
        if not source_asset:
             self.report({'WARNING'}, f"Source asset '{source_asset_repr.name}' must be from 'Current File' library.")
             return {'CANCELLED'}
        if not target_asset:
             self.report({'WARNING'}, f"Target asset '{target_asset_repr.name}' must be from 'Current File' library.")
             return {'CANCELLED'}

        source_preview = source_asset.preview
        if not source_preview:
            self.report({'WARNING'}, f"Source asset '{source_asset.name}' has no thumbnail data.")
            return {'CANCELLED'}

        target_asset.asset_generate_preview()
        target_preview = target_asset.preview

        target_preview.image_size = source_preview.image_size
        target_preview.image_pixels.foreach_set(source_preview.image_pixels)

        target_asset.asset_clear()
        target_asset.asset_mark()

        self.report({'INFO'}, f"Copied thumbnail from '{source_asset.name}' to '{target_asset.name}'.")
        return {'FINISHED'}

class ASSET_OT_download_thumbnail(bpy.types.Operator):
    """Saves the active asset's thumbnail to a file on disk"""
    bl_idname = "asset.download_thumbnail"
    bl_label = "Save Thumbnail to Disk"
    bl_options = {'REGISTER'}

    filepath: StringProperty(subtype="FILE_PATH")
    temp_image_name: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.area.ui_type == 'ASSETS'

    def invoke(self, context, event):
        if not NUMPY_AVAILABLE:
            self.report({'ERROR'}, "Numpy is required for this operation, but is not available.")
            return {'CANCELLED'}
        
        if not hasattr(context, 'selected_assets') or not context.selected_assets:
            self.report({'WARNING'}, "Please select an asset first.")
            return {'CANCELLED'}

        active_asset_repr = context.asset
        
        if not active_asset_repr and len(context.selected_assets) == 1:
            active_asset_repr = context.selected_assets[0]

        if not active_asset_repr:
            self.report({'WARNING'}, "Could not determine the active asset. Please re-select it.")
            return {'CANCELLED'}
            
        active_asset = active_asset_repr.local_id
        
        if not active_asset:
            self.report({'WARNING'}, f"Asset '{active_asset_repr.name}' must be from 'Current File' to save its thumbnail.")
            return {'CANCELLED'}

        preview = active_asset.preview
        if not preview or not preview.image_pixels_float:
            self.report({'WARNING'}, "Active asset has no floating-point preview data to save.")
            return {'CANCELLED'}
        
        pixels_as_floats_list = preview.image_pixels_float
        pixel_count = len(pixels_as_floats_list)
        if pixel_count == 0:
            self.report({'WARNING'}, "Active asset's preview has no pixel data.")
            return {'CANCELLED'}

        side_length = int((pixel_count / 4) ** 0.5)
        if side_length * side_length * 4 != pixel_count:
            self.report({'WARNING'}, "Could not determine valid preview dimensions from pixel data.")
            return {'CANCELLED'}

        width, height = side_length, side_length

        # OPTIMIZED: Convert the Python list to a numpy array for a massive speedup
        # when passing the data to Blender's internal C-API.
        pixels_as_floats_numpy = np.array(pixels_as_floats_list, dtype=np.float32)

        self.temp_image_name = f"temp_thumbnail_{hash(self)}" 
        temp_image = bpy.data.images.new(self.temp_image_name, width=width, height=height, alpha=True)
        
        temp_image.colorspace_settings.name = 'Non-Color'
        
        # Pass the numpy array to foreach_set for efficient data transfer.
        temp_image.pixels.foreach_set(pixels_as_floats_numpy)

        self.filepath = f"{active_asset.name}.png"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        temp_image = bpy.data.images.get(self.temp_image_name)
        if not temp_image:
            self.report({'WARNING'}, "Temporary thumbnail image was lost.")
            return {'CANCELLED'}
        
        temp_image.filepath_raw = self.filepath
        temp_image.file_format = 'PNG'
        temp_image.save()
        bpy.data.images.remove(temp_image)

        self.report({'INFO'}, f"Saved thumbnail to: {self.filepath}")
        return {'FINISHED'}

# -----------------------------------------------------------------------------
# UI PANEL
# -----------------------------------------------------------------------------

class ASSET_PT_thumbnail_kit(bpy.types.Panel):
    """Creates a Panel in the Asset Browser's Sidebar"""
    bl_label = "Thumbnail Toolz"
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_category = "Thumbnail Toolz"

    @classmethod
    def poll(cls, context):
        return context.area.ui_type == 'ASSETS'

    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Manual Copy", icon='COPYDOWN')
        col = box.column(align=True)
        col.operator(ASSET_OT_copy_selected_to_active.bl_idname, icon='CON_TRANSLIKE')
        col.label(text="1. Click Source Asset")
        col.label(text="2. Shift+Click Target Asset")

        box = layout.box()
        box.label(text="Export Thumbnail", icon='DISK_DRIVE')
        box.operator(ASSET_OT_download_thumbnail.bl_idname, icon='FILE_IMAGE')

# -----------------------------------------------------------------------------
# REGISTRATION
# -----------------------------------------------------------------------------

classes = (
    ASSET_OT_copy_selected_to_active,
    ASSET_OT_download_thumbnail,
    ASSET_PT_thumbnail_kit,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

