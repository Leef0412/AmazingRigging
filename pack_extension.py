#!/usr/bin/env python3
"""
打包 AmazingRigging 为 Blender Extension 格式
"""
import os
import zipfile
import shutil
from pathlib import Path

# 配置
PLUGIN_DIR = Path(__file__).parent
OUTPUT_DIR = PLUGIN_DIR  # 输出到根目录
ZIP_NAME = "amazing_rigging-1.0.0.zip"

# 需要包含的模块文件
MODULE_FILES = [
    "__init__.py",
    "ui_panel.py",
    "ui_layer_editor.py",
    "op_scripts.py",
    "ui_bone_properties.py",
    "utils_bone_data.py",
    "utils_set_bone_config.py",
    "utils_fk_ik_chain.py",
]

def create_package():
    """创建 Blender extension 格式的 zip 包"""
    zip_path = OUTPUT_DIR / ZIP_NAME

    # 删除旧的 zip 文件（如果存在）
    if zip_path.exists():
        zip_path.unlink()
        print(f"已删除旧文件: {zip_path}")

    print(f"\n开始打包 AmazingRigging...")
    print(f"输出文件: {zip_path}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # blender_manifest.toml 放 zip 根目录（add-on 格式）
        manifest_path = PLUGIN_DIR / "blender_manifest.toml"
        if manifest_path.exists():
            zipf.write(manifest_path, "blender_manifest.toml")
            print(f"  [OK] 添加: blender_manifest.toml")
        else:
            print(f"  [SKIP] blender_manifest.toml 不存在")

        # 模块文件直接放 zip 根目录（add-on 格式）
        for file_name in MODULE_FILES:
            file_path = PLUGIN_DIR / file_name
            if file_path.exists():
                zipf.write(file_path, file_name)
                print(f"  [OK] 添加: {file_name}")
            else:
                print(f"  [SKIP] 跳过 (不存在): {file_name}")
    
    # 显示结果
    zip_size = zip_path.stat().st_size
    print(f"\n[OK] 打包完成!")
    print(f"  文件: {zip_path}")
    print(f"  大小: {zip_size / 1024:.2f} KB")
    
    # 验证 zip 内容
    print(f"\n验证 zip 内容:")
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for name in zipf.namelist():
            print(f"  - {name}")
    
    return zip_path

if __name__ == "__main__":
    create_package()
