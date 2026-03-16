#!/usr/bin/env python3
"""Test que les trous du fond TANDEMBOX sont bien générés dans les figures."""

import sys
sys.path.insert(0, '/Users/lenapatarin/Documents/ANNEE1/code')

from export_manager import get_all_machining_plans_figures
from project_definitions import ARMOIRES

# Prise d'une config test simple
print("Testing TANDEMBOX drawer bottom holes generation...")
print("-" * 60)

# Config avec TANDEMBOX
project_data_tandembox = {
    'armoires': [
        {
            'ref': 'TANDEMBOX-TEST',
            'profondeur': 500,
            'hauteur': 900,
            'type': 'TANDEMBOX',
            'drawer_config_set': {
                'type': 'CUSTOM',
                'groupes': [
                    {'nombre': 1, 'hauteur': 300, 'systeme': 'TANDEMBOX', 'tech_type': 'K'},
                ]
            }
        }
    ]
}

session_state_mock = type('obj', (object,), {
    'unit_select': 'Millimètres',
    'unit_coeff': 1.0,
    'project_data': project_data_tandembox,
    'armoires': project_data_tandembox['armoires'],
})()

import streamlit as st
st.session_state = session_state_mock

try:
    figures = get_all_machining_plans_figures()
    print(f"✅ Generated {len(figures)} figures")
    
    # Chercher le fond TANDEMBOX
    for title, fig in figures:
        if 'Fond' in title and 'TANDEMBOX' in title:
            print(f"\n📋 Found: {title}")
            # Vérifier dans data de layout...
            if hasattr(fig, 'data') and len(fig.data) > 0:
                # Les trous sont dessinés comme scatter points
                scatter_count = sum(1 for trace in fig.data if 'scatter' in trace.type.lower())
                print(f"   - Figure has {scatter_count} scatter traces (holes/points)")
                if scatter_count > 0:
                    print(f"   ✅ Holes are present in the figure!")
                else:
                    print(f"   ⚠️  No holes found in figure")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
