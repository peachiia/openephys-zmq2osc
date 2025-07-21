#!/usr/bin/env python3
"""Build script for creating distributable binaries."""

import os
import sys
import platform
import subprocess
from pathlib import Path


def get_platform_suffix():
    """Get platform-specific suffix for binary names."""
    system = platform.system().lower()
    arch = platform.machine().lower()
    
    # Normalize architecture names
    if arch in ['x86_64', 'amd64']:
        arch = 'x64'
    elif arch in ['aarch64', 'arm64']:
        arch = 'arm64'
    elif arch in ['i386', 'i686']:
        arch = 'x86'
    
    return f"{system}-{arch}"


def run_command(cmd, cwd=None):
    """Run a command and handle errors."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def create_pyinstaller_spec():
    """Create PyInstaller spec file."""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/openephys_zmq2osc/main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'openephys_zmq2osc.core.services',
        'openephys_zmq2osc.core.events', 
        'openephys_zmq2osc.core.models',
        'openephys_zmq2osc.interfaces',
        'openephys_zmq2osc.config',
        'zmq.backend.cython',
        'zmq.backend',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='openephys-zmq2osc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    
    with open('openephys-zmq2osc.spec', 'w') as f:
        f.write(spec_content)
    
    print("Created PyInstaller spec file: openephys-zmq2osc.spec")


def build_binary():
    """Build the binary using PyInstaller."""
    # Ensure we're in the project root
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("Building binary with PyInstaller...")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version}")
    
    # Create spec file if it doesn't exist
    spec_file = Path('openephys-zmq2osc.spec')
    if not spec_file.exists():
        create_pyinstaller_spec()
    
    # Run PyInstaller
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        str(spec_file)
    ]
    
    if not run_command(cmd):
        print("Build failed!")
        return False
    
    # Check if binary was created
    platform_suffix = get_platform_suffix()
    
    if platform.system() == 'Windows':
        binary_name = 'openephys-zmq2osc.exe'
    else:
        binary_name = 'openephys-zmq2osc'
    
    binary_path = Path('dist') / binary_name
    
    if binary_path.exists():
        # Rename binary with platform suffix
        new_name = f"openephys-zmq2osc-{platform_suffix}"
        if platform.system() == 'Windows':
            new_name += '.exe'
        
        new_path = binary_path.parent / new_name
        binary_path.rename(new_path)
        
        print(f"✅ Binary created successfully: {new_path}")
        print(f"Binary size: {new_path.stat().st_size / (1024*1024):.1f} MB")
        
        return True
    else:
        print("❌ Binary not found after build!")
        return False


def test_binary():
    """Test the built binary."""
    platform_suffix = get_platform_suffix()
    binary_name = f"openephys-zmq2osc-{platform_suffix}"
    if platform.system() == 'Windows':
        binary_name += '.exe'
    
    binary_path = Path('dist') / binary_name
    
    if not binary_path.exists():
        print(f"Binary not found: {binary_path}")
        return False
    
    print("Testing binary...")
    
    # Test version flag
    cmd = [str(binary_path), '--version']
    if run_command(cmd):
        print("✅ Binary version test passed")
    else:
        print("❌ Binary version test failed")
        return False
    
    # Test help flag
    cmd = [str(binary_path), '--help']
    if run_command(cmd):
        print("✅ Binary help test passed")
    else:
        print("❌ Binary help test failed")
        return False
    
    return True


def main():
    """Main build function."""
    if len(sys.argv) > 1:
        if sys.argv[1] == 'spec':
            create_pyinstaller_spec()
            return
        elif sys.argv[1] == 'test':
            if test_binary():
                print("All tests passed!")
            else:
                print("Some tests failed!")
                sys.exit(1)
            return
    
    # Full build process
    print("Starting build process...")
    
    if not build_binary():
        print("Build failed!")
        sys.exit(1)
    
    if not test_binary():
        print("Binary tests failed!")
        sys.exit(1)
    
    print("\n🎉 Build completed successfully!")
    print("\nTo distribute the binary:")
    print("1. Test it on your target systems")
    print("2. Package it with any required configuration files") 
    print("3. Provide clear usage instructions")


if __name__ == '__main__':
    main()