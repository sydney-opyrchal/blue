"""
Simulated asset fleet for New Glenn manufacturing floor.

Topic naming follows a Sparkplug-B-inspired structure:
    factory/<area>/<cell>/<asset>/<metric>

Areas reflect actual New Glenn build process:
  - tank-fab: friction stir welding of cryogenic tank barrels (Ingersoll Mongoose)
  - composites: AFP (automated fiber placement) for fairings + adapters
  - chem-proc: chemical processing facility (new in 2025)
  - 2cat: Second Stage Cleaning and Testing
  - hif: Hardware Integration Facility
"""

ASSETS = [
    {
        "id": "FSW-01",
        "name": "Friction Stir Welder 01",
        "area": "tank-fab",
        "cell": "bay-1",
        "type": "fsw",
        "x": 120, "y": 140,
        "metrics": {
            "spindle_rpm":    {"nominal": 800,  "noise": 15,   "redline_high": 950,  "redline_low": 600},
            "tool_temp_c":    {"nominal": 480,  "noise": 8,    "redline_high": 550,  "redline_low": 400},
            "axial_force_kn": {"nominal": 28,   "noise": 1.2,  "redline_high": 35,   "redline_low": 20},
            "travel_mm_s":    {"nominal": 2.5,  "noise": 0.1,  "redline_high": 3.5,  "redline_low": 1.5},
        },
    },
    {
        "id": "FSW-02",
        "name": "Friction Stir Welder 02",
        "area": "tank-fab",
        "cell": "bay-2",
        "type": "fsw",
        "x": 120, "y": 240,
        "metrics": {
            "spindle_rpm":    {"nominal": 820,  "noise": 15,   "redline_high": 950,  "redline_low": 600},
            "tool_temp_c":    {"nominal": 475,  "noise": 8,    "redline_high": 550,  "redline_low": 400},
            "axial_force_kn": {"nominal": 27,   "noise": 1.2,  "redline_high": 35,   "redline_low": 20},
            "travel_mm_s":    {"nominal": 2.5,  "noise": 0.1,  "redline_high": 3.5,  "redline_low": 1.5},
        },
    },
    {
        "id": "AFP-01",
        "name": "Automated Fiber Placement 01",
        "area": "composites",
        "cell": "bay-3",
        "type": "afp",
        "x": 320, "y": 140,
        "metrics": {
            "head_temp_c":    {"nominal": 175, "noise": 4,    "redline_high": 210,  "redline_low": 140},
            "lay_rate_kg_h":  {"nominal": 12,  "noise": 0.5,  "redline_high": 18,   "redline_low": 6},
            "compaction_n":   {"nominal": 600, "noise": 25,   "redline_high": 800,  "redline_low": 400},
            "tow_tension_n":  {"nominal": 18,  "noise": 1,    "redline_high": 25,   "redline_low": 10},
        },
    },
    {
        "id": "AFP-02",
        "name": "Automated Fiber Placement 02",
        "area": "composites",
        "cell": "bay-4",
        "type": "afp",
        "x": 320, "y": 240,
        "metrics": {
            "head_temp_c":    {"nominal": 178, "noise": 4,    "redline_high": 210,  "redline_low": 140},
            "lay_rate_kg_h":  {"nominal": 11,  "noise": 0.5,  "redline_high": 18,   "redline_low": 6},
            "compaction_n":   {"nominal": 610, "noise": 25,   "redline_high": 800,  "redline_low": 400},
            "tow_tension_n":  {"nominal": 19,  "noise": 1,    "redline_high": 25,   "redline_low": 10},
        },
    },
    {
        "id": "AUTO-01",
        "name": "Composite Autoclave 01",
        "area": "composites",
        "cell": "bay-5",
        "type": "autoclave",
        "x": 320, "y": 340,
        "metrics": {
            "vessel_temp_c":  {"nominal": 180, "noise": 2,    "redline_high": 200,  "redline_low": 20},
            "vessel_psi":     {"nominal": 100, "noise": 1.5,  "redline_high": 110,  "redline_low": 0},
            "vacuum_torr":    {"nominal": 5,   "noise": 0.5,  "redline_high": 25,   "redline_low": 0},
        },
    },
    {
        "id": "CNC-01",
        "name": "5-Axis Mill 01",
        "area": "chem-proc",
        "cell": "bay-6",
        "type": "cnc",
        "x": 520, "y": 140,
        "metrics": {
            "spindle_rpm":    {"nominal": 9500, "noise": 200, "redline_high": 12000, "redline_low": 1000},
            "spindle_load":   {"nominal": 65,   "noise": 5,   "redline_high": 90,    "redline_low": 0},
            "coolant_temp_c": {"nominal": 22,   "noise": 0.5, "redline_high": 35,    "redline_low": 10},
        },
    },
    {
        "id": "CNC-02",
        "name": "5-Axis Mill 02",
        "area": "chem-proc",
        "cell": "bay-7",
        "type": "cnc",
        "x": 520, "y": 240,
        "metrics": {
            "spindle_rpm":    {"nominal": 9700, "noise": 200, "redline_high": 12000, "redline_low": 1000},
            "spindle_load":   {"nominal": 60,   "noise": 5,   "redline_high": 90,    "redline_low": 0},
            "coolant_temp_c": {"nominal": 22,   "noise": 0.5, "redline_high": 35,    "redline_low": 10},
        },
    },
    {
        "id": "CR-2CAT",
        "name": "2CAT Clean Room",
        "area": "2cat",
        "cell": "high-bay",
        "type": "env",
        "x": 720, "y": 190,
        "metrics": {
            "particles_p_ft3": {"nominal": 8000, "noise": 400, "redline_high": 100000, "redline_low": 0},
            "humidity_pct":    {"nominal": 45,   "noise": 1,   "redline_high": 60,     "redline_low": 30},
            "temp_c":          {"nominal": 21,   "noise": 0.3, "redline_high": 24,     "redline_low": 18},
        },
    },
    {
        "id": "HIF-CRANE",
        "name": "HIF Bridge Crane",
        "area": "hif",
        "cell": "high-bay",
        "type": "crane",
        "x": 720, "y": 290,
        "metrics": {
            "load_kg":      {"nominal": 0,    "noise": 50,  "redline_high": 50000, "redline_low": -100},
            "trolley_pos":  {"nominal": 50,   "noise": 0.2, "redline_high": 100,   "redline_low": 0},
        },
    },
]

# Map asset type -> human label for the floor map
ASSET_TYPE_LABEL = {
    "fsw": "Friction Stir Weld",
    "afp": "Automated Fiber Placement",
    "autoclave": "Autoclave",
    "cnc": "5-Axis Mill",
    "env": "Clean Room",
    "crane": "Bridge Crane",
}
