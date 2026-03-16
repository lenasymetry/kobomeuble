#!/usr/bin/env python3
"""Test script to verify hole count in exported DXF"""

import sys
import os
import tempfile
from pathlib import Path

# Import after adding path
sys.path.insert(0, str(Path(__file__).parent))

import ezdxf
from export_manager import generate_stacked_html_plans

def count_holes_in_dxf(dxf_path):
    """Count circles (holes) in DXF file by diameter"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
    except Exception as e:
        print(f"❌ Error reading {dxf_path}: {e}")
        return None
    
    circles_by_diameter = {}
    total_circles = 0
    
    try:
        msp = doc.modelspace()
        for entity in msp.query('CIRCLE'):
            total_circles += 1
            radius = entity.dxf.radius
            diam = round(radius * 2, 1)
            diam_str = f"Ø{diam:.0f}"
            circles_by_diameter[diam_str] = circles_by_diameter.get(diam_str, 0) + 1
    except Exception as e:
        print(f"❌ Error processing entities: {e}")
        return None
    
    return total_circles, circles_by_diameter


def main():
    # Create temp file for DXF
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        dxf_output = Path(f.name)
    
    print("=" * 60)
    print("TESTING DXF HOLE EXPORT")
    print("=" * 60)
    
    # Test with dummy cabinets data first
    print(f"\n1. Creating test export...")
    try:
        # We need to call generate_stacked_html_plans directly with test data
        # First, let's try with empty data
        dxf_bytes, success = generate_stacked_html_plans(
            cabinets_to_process=[],
            indices_to_process=[],
            output_format='dxf'
        )
        
        if not success or not dxf_bytes:
            print(f"   ⚠️  No data to export (empty cabinet list)")
            dxf_output.unlink(missing_ok=True)
            return None
        
        # Write to file
        if isinstance(dxf_bytes, bytes):
            dxf_output.write_bytes(dxf_bytes)
        else:
            dxf_output.write_text(dxf_bytes)
        
        print(f"   ✓ Export completed")
        print(f"   ✓ File created: {dxf_output.stat().st_size} bytes")
    except Exception as e:
        print(f"   ❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        dxf_output.unlink(missing_ok=True)
        return False
    
    # Check if file was created
    if not dxf_output.exists() or dxf_output.stat().st_size == 0:
        print(f"   ❌ DXF file is empty or not created")
        dxf_output.unlink(missing_ok=True)
        return None
    
    # Count holes
    print(f"\n2. Analyzing hole count...")
    result = count_holes_in_dxf(dxf_output)
    
    if result is None:
        print("   ❌ Failed to analyze DXF")
        dxf_output.unlink(missing_ok=True)
        return False
    
    total_holes, by_diameter = result
    print(f"   Total holes found: {total_holes}")
    
    if not by_diameter:
        print("   ⚠️  No circles found")
        dxf_output.unlink(missing_ok=True)
        return None
    
    # Print by diameter
    for diam_str in sorted(by_diameter.keys()):
        count = by_diameter[diam_str]
        print(f"      {diam_str}: {count} holes")
    
    # Baseline comparison
    print(f"\n3. Comparison with baseline:")
    print(f"   Baseline (previous): Ø3: 36, Ø5: 38, Ø8: 96 = 170 total")
    print(f"   Current: Total = {total_holes}")
    
    if total_holes > 0:
        print(f"   Δ = {total_holes - 170:+d} holes")
        if total_holes > 170:
            print("\n✅ IMPROVEMENT: More holes are now being exported!")
        elif total_holes == 170:
            print("\n⚠️  No change: Same hole count as before")
        else:
            print("\n❌ REGRESSION: Fewer holes than before!")
    else:
        print("   ⚠️  No holes exported")
    
    # Clean up
    print(f"\n4. Cleaning up test file...")
    dxf_output.unlink(missing_ok=True)
    print("   ✓ Done")
    
    return total_holes > 0 and total_holes != 170


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
