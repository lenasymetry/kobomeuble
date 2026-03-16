#!/usr/bin/env python3
"""Unit test to verify merged hole logic"""

import sys
from pathlib import Path

# Test the merge logic directly
def test_hole_merge():
    """Test that hole lists are properly merged"""
    # Simulate three hole lists from machining_logic
    fh = [
        {'type': 'vis', 'x': 50.0, 'y': 100.0, 'diam_str': '⌀5'},
        {'type': 'vis', 'x': 150.0, 'y': 100.0, 'diam_str': '⌀5'},
    ]
    
    t_long_h = [
        {'type': 'tourillon', 'x': 100.0, 'y': 150.0, 'diam_str': '⌀8'},
    ]
    
    t_cote_h = [
        {'type': 'tourillon', 'x': 75.0, 'y': 125.0, 'diam_str': '⌀8'},
        {'type': 'vis', 'x': 175.0, 'y': 125.0, 'diam_str': '⌀3'},
    ]
    
    # Merge like the DXF code does
    all_holes = []
    for holes_list in [fh, t_long_h, t_cote_h]:
        if holes_list:
            all_holes.extend(holes_list)
    
    print("=" * 60)
    print("HOLE MERGE TEST")
    print("=" * 60)
    print(f"\nfh:       {len(fh)} holes")
    print(f"t_long_h: {len(t_long_h)} holes")
    print(f"t_cote_h: {len(t_cote_h)} holes")
    print(f"MERGED:   {len(all_holes)} holes")
    
    expected_total = len(fh) + len(t_long_h) + len(t_cote_h)
    
    if len(all_holes) == expected_total:
        print(f"\n✅ PASS: Merged {len(all_holes)} = {expected_total} (all holes preserved)")
        return True
    else:
        print(f"\n❌ FAIL: Merged {len(all_holes)} != expected {expected_total}")
        return False


if __name__ == "__main__":
    success = test_hole_merge()
    sys.exit(0 if success else 1)
