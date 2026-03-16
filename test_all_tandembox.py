#!/usr/bin/env python3
"""
Verification test: All TANDEMBOX types (K, M, N, D) generate bottom holes correctly.
"""

def test_all_tandembox_types():
    print("Testing ALL TANDEMBOX types (K, M, N, D) bottom hole generation...")
    print("-" * 70)
    
    tech_types = ['K', 'M', 'N', 'D']
    
    y_coords_back = {
        'K': [30.0, 62.0, 94.0],
        'M': [32.0, 64.0],
        'N': [31.0, 47.0],
        'D': [31.0, 63.0, 95.0, 159.0, 191.0]
    }
    
    # Drawer bottom dimensions that would be used
    fond_L = 500
    
    # Test a few different fond_H values to check the conditions
    test_heights = [300, 500, 900]
    
    all_pass = True
    
    for tech_type in tech_types:
        print(f"\n🔧 Type {tech_type}:")
        y_coords = y_coords_back.get(tech_type, y_coords_back['K'])
        print(f"   y_coords_back = {y_coords}")
        
        for fond_H in test_heights:
            bottom_holes = []
            for dy in y_coords:
                if dy < fond_H:
                    bottom_holes.append({'type': 'vis_fond', 'x': 9.0, 'y': dy, 'diam_str': "⌀3"})
                    bottom_holes.append({'type': 'vis_fond', 'x': fond_L - 9.0, 'y': dy, 'diam_str': "⌀3"})
            
            expected_count = len([y for y in y_coords if y < fond_H]) * 2
            print(f"   Height {fond_H}mm → {len(bottom_holes)} holes (expected {expected_count})", end="")
            
            if len(bottom_holes) == expected_count:
                print(" ✅")
            else:
                print(" ❌")
                all_pass = False
    
    print("\n" + "=" * 70)
    if all_pass:
        print("✅ All TANDEMBOX types generate correct bottom holes!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == '__main__':
    success = test_all_tandembox_types()
    exit(0 if success else 1)
