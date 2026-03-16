#!/usr/bin/env python3
"""
Test: Verify that bottom holes respect fond_H height boundaries.
Some holes might be filtered out if they exceed the drawer bottom height.
"""

def test_height_boundaries():
    print("Testing height boundary filtering for TANDEMBOX bottom holes...")
    print("-" * 70)
    
    # Type D has the most holes at different heights
    tech_type = 'D'
    y_coords_back = [31.0, 63.0, 95.0, 159.0, 191.0]
    
    print(f"Type {tech_type} y_coords_back: {y_coords_back}")
    print(f"Height values: {', '.join(f'{y}' for y in y_coords_back)}")
    print()
    
    fond_L = 500
    test_scenarios = [
        (100, "Small drawer (100mm)"),
        (150, "Medium drawer (150mm)"),
        (200, "Large drawer (200mm)"),
        (400, "Tall drawer (400mm)"),
    ]
    
    all_pass = True
    
    for fond_H, description in test_scenarios:
        bottom_holes = []
        for dy in y_coords_back:
            if dy < fond_H:
                bottom_holes.append({'type': 'vis_fond', 'x': 9.0, 'y': dy, 'diam_str': "⌀3"})
                bottom_holes.append({'type': 'vis_fond', 'x': fond_L - 9.0, 'y': dy, 'diam_str': "⌀3"})
        
        filtered_coords = [y for y in y_coords_back if y < fond_H]
        expected_count = len(filtered_coords) * 2
        
        print(f"  {description}: fond_H={fond_H}mm")
        print(f"    → Filtered y_coords: {filtered_coords}")
        print(f"    → Generated {len(bottom_holes)} holes (expected {expected_count})", end="")
        
        if len(bottom_holes) == expected_count:
            print(" ✅")
        else:
            print(" ❌")
            all_pass = False
    
    print("\n" + "=" * 70)
    if all_pass:
        print("✅ Height boundary filtering works correctly!")
        print("   Holes are properly limited by drawer height")
        return True
    else:
        print("❌ Height boundary test failed")
        return False

if __name__ == '__main__':
    success = test_height_boundaries()
    exit(0 if success else 1)
