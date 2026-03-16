#!/usr/bin/env python3
"""
Test DXF: Generate a small DXF file with test triangles only.
This will create a visual test file to verify triangles are complete.
"""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

try:
    from dxf_export.symbols import add_empty_triangle, add_filled_triangle
    import ezdxf
    
    print("Creating test DXF with triangles...")
    print("-" * 70)
    
    # Create a new DXF document with standard A4 layout
    dxf = ezdxf.new()
    msp = dxf.modelspace()
    
    # Test 1: Empty triangle (outline only)
    print("✅ Adding empty triangle at (100, 100)...")
    add_empty_triangle(msp, center=(100, 100), size=30, rotation=0, layer="SYMBOLS")
    
    # Test 2: Filled triangle
    print("✅ Adding filled triangle at (200, 100)...")
    add_filled_triangle(msp, center=(200, 100), size=30, rotation=0, layer="SYMBOLS")
    
    # Test 3: Rotated empty triangle
    print("✅ Adding rotated empty triangle at (300, 100)...")
    add_empty_triangle(msp, center=(300, 100), size=30, rotation=45, layer="SYMBOLS")
    
    # Test 4: Rotated filled triangle
    print("✅ Adding rotated filled triangle at (400, 100)...")
    add_filled_triangle(msp, center=(400, 100), size=30, rotation=45, layer="SYMBOLS")
    
    # Save to file
    output_file = '/Users/lenapatarin/Documents/ANNEE1/code/test_triangles_output.dxf'
    dxf.saveas(output_file)
    print(f"\n✅ DXF file saved to: {output_file}")
    print("\nInstructions:")
    print("1. Open test_triangles_output.dxf in AutoCAD")
    print("2. Verify ALL triangles have 3 complete sides")
    print("3. Empty triangles should show outline only")
    print("4. Filled triangles should show solid fill")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
