"""
NextFlex Project Portal — Database initialization & seed.

Generates a comprehensive, deterministic corpus that fits comfortably
in Render free tier (512 MB RAM, <10 sec generation, ~15 MB on disk):
  - ~400 projects across PC 1.0 through 10.2
  - ~3,000 entities (materials, processes, performance metrics)
  - ~5,000 typed relationships
  - ~6,000 text chunks with FTS5 search
  - 30 congressional districts
  - 6 DoD PEOs
  - ~30 commercial deployments

Run: python init_db.py [--reset]
"""

import argparse
import hashlib
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "nextflex.db"

SCHEMA = """
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS entities;
DROP TABLE IF EXISTS relationships;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS districts;
DROP TABLE IF EXISTS deployments;
DROP TABLE IF EXISTS peos;
DROP TABLE IF EXISTS projects_fts;
DROP TABLE IF EXISTS chunks_fts;

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    project_call TEXT NOT NULL,
    title TEXT NOT NULL,
    lead_institution TEXT,
    principal_investigators TEXT,
    co_investigators TEXT,
    industry_partners TEXT,
    start_date TEXT,
    end_date TEXT,
    funding_amount INTEGER,
    abstract TEXT,
    focus_area TEXT,
    materials_used TEXT,
    processes_used TEXT,
    outcomes TEXT,
    status TEXT,
    publications TEXT,
    patents TEXT,
    keywords TEXT,
    congressional_district TEXT,
    trl_start INTEGER,
    trl_end INTEGER,
    classification TEXT DEFAULT 'public',
    peo TEXT
);
CREATE INDEX idx_pc ON projects (project_call);
CREATE INDEX idx_focus ON projects (focus_area);
CREATE INDEX idx_inst ON projects (lead_institution);
CREATE INDEX idx_district ON projects (congressional_district);
CREATE INDEX idx_classif ON projects (classification);

CREATE VIRTUAL TABLE projects_fts USING fts5(
    id UNINDEXED, title, abstract, principal_investigators,
    lead_institution, materials_used, processes_used, keywords, focus_area
);

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    subtype TEXT,
    name TEXT NOT NULL,
    properties TEXT,
    source_project_ids TEXT,
    classification TEXT DEFAULT 'public'
);
CREATE INDEX idx_ent_type ON entities (type);
CREATE INDEX idx_ent_subtype ON entities (subtype);

CREATE TABLE relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source_project_id TEXT
);
CREATE INDEX idx_rel_from ON relationships (from_id);
CREATE INDEX idx_rel_to ON relationships (to_id);

CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    section TEXT,
    page INTEGER,
    text TEXT NOT NULL,
    classification TEXT DEFAULT 'public'
);
CREATE INDEX idx_chunk_project ON chunks (project_id);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    id UNINDEXED, text, project_id UNINDEXED, section UNINDEXED
);

CREATE TABLE districts (
    code TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    representative TEXT,
    party TEXT,
    project_count INTEGER DEFAULT 0,
    total_funding INTEGER DEFAULT 0,
    notable_orgs TEXT
);

CREATE TABLE deployments (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    organization TEXT NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    source_project_ids TEXT,
    district TEXT,
    peo TEXT,
    deploy_date TEXT
);

CREATE TABLE peos (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    full_name TEXT,
    location TEXT,
    relevance TEXT,
    program_offices TEXT,
    active_programs INTEGER DEFAULT 0,
    district TEXT
);
"""

DISTRICTS = [
    ("MA-03", "Massachusetts", "Lori Trahan", "D", ["UMass Lowell", "PERC/RURI"]),
    ("MA-05", "Massachusetts", "Katherine Clark", "D", ["MIT Lincoln Lab"]),
    ("CT-04", "Connecticut", "Jim Himes", "D", ["Raytheon Technologies"]),
    ("VA-10", "Virginia", "Suhas Subramanyam", "D", ["Northrop Grumman"]),
    ("VA-08", "Virginia", "Don Beyer", "D", ["PEO Soldier (Fort Belvoir)"]),
    ("MD-05", "Maryland", "Steny Hoyer", "D", ["Lockheed Martin"]),
    ("MD-01", "Maryland", "Andy Harris", "R", ["PEO IEW&S", "PEO C3T (APG)"]),
    ("AZ-01", "Arizona", "David Schweikert", "R", ["Optomec Inc."]),
    ("AZ-04", "Arizona", "Greg Stanton", "D", ["Honeywell Aerospace", "ASU FlexTech"]),
    ("CA-12", "California", "Nancy Pelosi", "D", ["UC Berkeley"]),
    ("CA-16", "California", "Sam Liccardo", "D", ["Stanford University"]),
    ("CA-17", "California", "Ro Khanna", "D", ["NextFlex HQ", "ANI Inc."]),
    ("CA-25", "California", "Raul Ruiz", "D", ["Lockheed Skunk Works"]),
    ("CA-26", "California", "Julia Brownley", "D", ["FlexTrate Technologies"]),
    ("DE-AL", "Delaware", "Sarah McBride", "D", ["DuPont Electronics"]),
    ("FL-15", "Florida", "Laurel Lee", "R", ["USSOCOM (MacDill)"]),
    ("GA-05", "Georgia", "Nikema Williams", "D", ["Georgia Tech"]),
    ("ID-02", "Idaho", "Mike Simpson", "R", ["American Semiconductor"]),
    ("IA-04", "Iowa", "Randy Feenstra", "R", ["Iowa State University"]),
    ("IN-04", "Indiana", "Jim Baird", "R", ["Purdue University"]),
    ("MN-05", "Minnesota", "Ilhan Omar", "D", ["Henkel Corporation"]),
    ("MO-08", "Missouri", "Jason Smith", "R", ["Brewer Science"]),
    ("NC-07", "North Carolina", "David Rouzer", "R", ["Fort Liberty / DEVCOM"]),
    ("NM-01", "New Mexico", "Melanie Stansbury", "D", ["Sandia National Labs"]),
    ("NY-19", "New York", "Josh Riley", "D", ["Cornell University"]),
    ("OH-01", "Ohio", "Greg Landsman", "D", ["GE Aerospace"]),
    ("OH-10", "Ohio", "Mike Turner", "R", ["ARL / Wright-Patterson"]),
    ("PA-15", "Pennsylvania", "Glenn Thompson", "R", ["Penn State ARL"]),
    ("TX-26", "Texas", "Brandon Gill", "R", ["DuPont (Texas)"]),
    ("WA-09", "Washington", "Adam Smith", "D", ["Boeing R&T"]),
]

PEOS = [
    ("PEO-Soldier", "PEO Soldier", "Program Executive Office Soldier", "Fort Belvoir, VA",
     "Wearable electronics, soldier-worn sensors, flexible displays, body-worn HE systems",
     ["PM SWAR", "PM Soldier Lethality"], "VA-08"),
    ("PEO-IEWS", "PEO IEW&S", "PEO Intelligence, Electronic Warfare & Sensors",
     "Aberdeen Proving Ground, MD",
     "Printed RF/antenna arrays, EW components, BST phase shifters",
     ["PM EW&C", "PM Positioning, Navigation & Timing"], "MD-01"),
    ("PEO-C3T", "PEO C3T", "PEO Command, Control, Communications - Tactical",
     "Aberdeen Proving Ground, MD",
     "Tactical networking, 5G infrastructure, conformal antennas",
     ["PM TN", "PM Mission Command"], "MD-01"),
    ("ARL-MM", "ARL Materials & Manufacturing", "U.S. Army Research Laboratory Materials & Mfg",
     "Adelphi, MD / Wright-Patterson, OH",
     "Defense materials research, manufacturing readiness, technology transition",
     ["SEDD", "WMRD"], "OH-10"),
    ("USSOCOM", "USSOCOM SOF AT&L", "Special Operations Forces Acquisition, Tech & Logistics",
     "MacDill AFB, FL",
     "SOF-specific HE: conformal antennas, lightweight sensors, mission-tailored circuits",
     ["PEO-SOF Warrior"], "FL-15"),
    ("AFLCMC", "AFLCMC", "Air Force Life Cycle Management Center",
     "Wright-Patterson AFB, OH",
     "AF acquisition for flexible electronics in aerospace platforms",
     ["AFRL Mat'l Mfg liaison"], "OH-10"),
]

LEAD_INSTITUTIONS = [
    ("UMass Lowell", "MA-03"), ("American Semiconductor", "ID-02"),
    ("GE Aerospace", "OH-01"), ("Boeing R&T", "WA-09"),
    ("Northrop Grumman", "VA-10"), ("Raytheon Technologies", "CT-04"),
    ("Lockheed Martin", "MD-05"), ("Honeywell Aerospace", "AZ-04"),
    ("Optomec Inc.", "AZ-01"), ("DuPont Electronics", "DE-AL"),
    ("Stanford University", "CA-16"), ("MIT Lincoln Lab", "MA-05"),
    ("Georgia Tech", "GA-05"), ("Purdue University", "IN-04"),
    ("UC Berkeley", "CA-12"), ("ASU FlexTech", "AZ-04"),
    ("Iowa State University", "IA-04"), ("Penn State ARL", "PA-15"),
    ("Brewer Science", "MO-08"), ("FlexTrate Technologies", "CA-26"),
    ("ANI Inc.", "CA-17"), ("Cornell University", "NY-19"),
    ("Henkel Corporation", "MN-05"), ("Lockheed Skunk Works", "CA-25"),
    ("Sandia National Labs", "NM-01"),
]

FOCUS_AREAS = [
    "Flexible Circuits", "Printed RF/Antennas", "Wearable Sensors",
    "Conformal Electronics", "Hybrid Packaging", "Printed Power Devices",
    "Flexible Displays", "Materials & Inks", "Reliability & Test",
    "Manufacturing Processes", "Soldier-Worn Systems", "Medical Devices",
    "IoT Sensor Nodes", "Phased Array Antennas", "Tunable Substrates",
]

CONDUCTIVE_INKS = [
    ("Silver nanoparticle ink (GenesINk PL1-120)", "GenesINk", {"solids_pct": 60, "diluent": "ethanol", "resistivity_ohm_m": 4.2e-8}),
    ("Copper ink (Electroninks CI-005)", "Electroninks", {"solids_pct": 35, "resistivity_ohm_m": 8.7e-8}),
    ("Silver flake ink (DuPont PE872)", "DuPont", {"solids_pct": 70, "resistivity_ohm_m": 6.2e-8}),
    ("Silver paste (Henkel ECI 1010)", "Henkel", {"resistivity_ohm_m": 5.1e-8}),
    ("Silver nanoparticle (NovaCentrix)", "NovaCentrix", {"solids_pct": 55, "resistivity_ohm_m": 4.8e-8}),
    ("Carbon conductive ink (Sun Chemical CRSN2442)", "Sun Chemical", {"sheet_resistance_ohm_sq": 25}),
]
DIELECTRIC_INKS = [
    ("BST sinterless dielectric (PERC/RURI)", "PERC/RURI", {"cure": "uv", "epsilon_r": 200, "tan_delta": 0.008, "rq_nm": 78}),
    ("Heraeus EL-P 5042 dielectric", "Heraeus", {"cure": "thermal", "epsilon_r": 3.5}),
    ("DuPont 5018 dielectric", "DuPont", {"cure": "thermal", "epsilon_r": 4.0}),
    ("Asahi CR-18G-KF", "Asahi", {"cure": "uv", "epsilon_r": 3.8}),
]
SUBSTRATES = [
    ("Kapton HN 25um polyimide", "DuPont", {"thickness_um": 25, "cte_ppm_k": 20, "dk_1ghz": 3.4}),
    ("Kapton HN 50um polyimide", "DuPont", {"thickness_um": 50, "cte_ppm_k": 20, "dk_1ghz": 3.4}),
    ("PEN substrate", "Teijin", {"thickness_um": 50, "cte_ppm_k": 18}),
    ("TPU flexible substrate", "BASF", {"thickness_um": 100, "cte_ppm_k": 150}),
    ("PET 75um", "DuPont", {"thickness_um": 75}),
    ("Glass-PI laminate", "DuPont", {"thickness_um": 75}),
]
ACTIVE_COMPONENTS = [
    ("Qorvo TGA2222 GaN MMIC", "Qorvo", {"part": "TGA2222", "tech": "150nm GaN-on-SiC", "freq_ghz": "8-12", "power_w": 10}),
    ("Analog Devices AD8009", "Analog Devices", {"part": "AD8009", "tech": "BiCMOS"}),
    ("Texas Instruments LMV851", "Texas Instruments", {"part": "LMV851", "tech": "CMOS"}),
]

PROCESSES = [
    ("Aerosol jet printing - Optomec AJ5X", "deposition", {"nozzle_um": 300, "speed_mm_s": 5}),
    ("Inkjet printing", "deposition", {"resolution_um": 50}),
    ("Screen printing", "deposition", {"thickness_um": 10}),
    ("Gravure printing", "deposition", {"speed_m_min": 5}),
    ("Laser sintering 830nm", "post_process", {"wavelength_nm": 830, "power_w": 2, "dwell_temp_c": 250}),
    ("Photonic flash sintering", "post_process", {"flash_us": 2000, "energy_j_cm2": 10}),
    ("Thermal cure 150C", "post_process", {"temp_c": 150, "duration_min": 30}),
    ("UV cure 365nm", "post_process", {"wavelength_nm": 365, "intensity_mw_cm2": 100}),
    ("Die attach Ag epoxy", "assembly", {"cure_c": 150, "cure_min": 60}),
    ("Wire bonding", "assembly", {"wire_um": 25}),
    ("Anisotropic conductive film", "assembly", {}),
    ("Reactive ion etching", "patterning", {"power_w": 100}),
]

PERF_TEMPLATES = [
    ("X-band patch antenna S-params", "s_parameters",
     {"freq_ghz": 10, "gain_db": (5.5, 7.0), "return_loss_db": (-22, -15), "bandwidth_mhz": (300, 450)}),
    ("Ka-band phased array element", "s_parameters",
     {"freq_ghz": 28, "gain_db": (4.5, 6.0), "return_loss_db": (-18, -12)}),
    ("BST phase shifter at 10 GHz", "s_parameters",
     {"freq_ghz": 10, "insertion_loss_db": (-2.5, -1.5), "isolation_db": (-32, -25), "phase_shift_deg": 90}),
    ("Power amplifier at 28 GHz", "power_efficiency",
     {"output_power_dbm": (26, 30), "pae_pct": (35, 45), "pulsed_power_w": (5, 12)}),
    ("Cu trace surface roughness", "physical_em",
     {"rq_nm": (80, 160), "platen_temp_c": (60, 120)}),
    ("Sheet resistance after thermal cycle", "physical_em",
     {"sheet_resistance_change_pct": (5, 25)}),
]

PI_FIRST = ["Vinod", "Alkim", "Oshadha", "Mark", "Shashi", "Pradeep", "Ramesh",
            "John", "Sarah", "David", "Karen", "Michael", "Lisa", "Robert",
            "Ahmed", "Wei", "Priya", "Hassan", "Elena", "James", "Yuki",
            "Carlos", "Amelia", "Peter", "Anand", "Beatrix", "Catherine",
            "Daniel", "Eleanor", "Felix", "Grace", "Henry", "Iris", "Julian"]
PI_LAST = ["Vokkarane", "Akyurtlu", "Ranasingha", "Allen", "Pal", "Kumar",
           "Patel", "Smith", "Johnson", "Chen", "Williams", "Brown", "Davis",
           "Garcia", "Miller", "Wilson", "Anderson", "Taylor", "Thomas",
           "Moore", "Martin", "Jackson", "Lee", "Park", "Singh", "Nguyen",
           "Mahmoud", "OBrien", "Schmidt", "Rossi"]

PC_DEFINITIONS = [
    ("PC 1.0", 2017, 12), ("PC 1.1", 2017, 14), ("PC 1.2", 2017, 16),
    ("PC 2.0", 2018, 16), ("PC 2.6", 2018, 18),
    ("PC 3.0", 2019, 18), ("PC 3.5", 2019, 16),
    ("PC 4.0", 2019, 16), ("PC 4.5", 2020, 18),
    ("PC 5.0", 2020, 20), ("PC 5.6", 2020, 18),
    ("PC 6.0", 2020, 20), ("PC 6.9", 2021, 20),
    ("PC 7.0", 2021, 18), ("PC 7.1", 2021, 18),
    ("PC 8.0", 2022, 22), ("PC 8.5", 2022, 18),
    ("PC 9.0", 2022, 20), ("PC 9.5", 2023, 18), ("PC 9.6", 2023, 18),
    ("PC 10.0", 2023, 20), ("PC 10.2", 2024, 16),
]

TITLE_TEMPLATES = {
    "Flexible Circuits": [
        "Multi-layer Flexible Interconnect Demonstrators for {app}",
        "High-Density Flex Circuit Architectures for {app}",
        "Reliability of Flexible Substrates in {env} Environments",
        "Roll-to-Roll Manufacturing of Flex Circuits for {app}",
    ],
    "Printed RF/Antennas": [
        "Conformal {band} Antenna Array on Flexible Substrates",
        "Printed {component} for {band} Communications",
        "Beam-Steerable {band} Phased Array Using Aerosol Jet Printing",
        "Low-Loss Printed {component} on {substrate} Substrate",
    ],
    "Wearable Sensors": [
        "Stretchable Strain Sensor for {app} Monitoring",
        "Skin-Conformal Biosensor Array with {feature}",
        "Wireless {sensor_type} Sensor Patch for Continuous Monitoring",
    ],
    "Conformal Electronics": [
        "Conformal Electronic Skin for {app}",
        "Curved-Surface Electronics Integration for {platform}",
        "Adaptive Conformal Sensors for {platform} Health Monitoring",
    ],
    "Hybrid Packaging": [
        "Advanced Hybrid Packaging for {device} Integration",
        "Fan-Out Wafer-Level Packaging on Flexible Substrate",
        "Die Attach Reliability for Flexible Hybrid Electronics",
    ],
    "Printed Power Devices": [
        "Printed Energy Storage for {app}",
        "Flexible Power Management IC Integration",
        "Printed Supercapacitors for Wearable Power",
    ],
    "Flexible Displays": [
        "Foldable {tech} Display Backplane",
        "High-Resolution Printed Display Driver Circuit",
    ],
    "Materials & Inks": [
        "Novel {ink_type} Ink Formulation for Extreme Environment Reliability",
        "Low-Temperature Sintering of {material} Conductive Inks",
        "BST Dielectric Nano-Ink for {band} Tunable Substrates",
        "{material} Ink Performance Characterization Study",
    ],
    "Reliability & Test": [
        "Accelerated Life Testing of Printed Conductors on {substrate}",
        "Failure Mode Analysis of Flexible Hybrid Assemblies",
        "Environmental Reliability of Printed Electronics in {env} Conditions",
    ],
    "Manufacturing Processes": [
        "High-Volume Aerosol Jet Manufacturing Process Development",
        "Roll-to-Roll Integration of Hybrid Components",
        "Process Optimization for {process} on Polyimide",
    ],
    "Soldier-Worn Systems": [
        "Body-Worn {sensor_type} Array for Soldier Lethality",
        "Lightweight Conformal Antenna for Dismounted Communications",
        "Helmet-Mounted Conformal Sensor Network",
    ],
    "Medical Devices": [
        "Implantable Flexible Sensor for {app} Monitoring",
        "Wearable ECG Patch with {feature}",
        "Stretchable Electrode Array for Neural Interfaces",
    ],
    "IoT Sensor Nodes": [
        "Self-Powered IoT Node with Printed {sensor_type} Sensor",
        "Energy-Harvesting Wireless Sensor Node",
        "Low-Power Wireless Sensor Patches for Industrial Monitoring",
    ],
    "Phased Array Antennas": [
        "Printed {band} Phased Array with PLTL-BST Phase Shifters",
        "Conformal {band} Beamforming Array",
        "Wide-Scan {band} Printed Phased Array Demonstrator",
    ],
    "Tunable Substrates": [
        "Voltage-Tunable BST Substrate for {band} RF Applications",
        "Reconfigurable RF Substrate with Sinterless Dielectric Inks",
        "Tunable Filter Network on Printed BST Substrate",
    ],
}

PLACEHOLDERS = {
    "{app}": ["health monitoring", "structural health monitoring", "asset tracking",
              "rehabilitation", "industrial automation", "vehicle telemetry"],
    "{env}": ["high-temperature", "high-vibration", "humidity-cycled", "saline",
              "thermal-cycled", "high-altitude"],
    "{band}": ["X-band", "Ku-band", "Ka-band", "S-band", "5G mm-wave", "L-band", "W-band"],
    "{component}": ["filter", "phase shifter", "switch matrix", "bandpass filter", "LNA"],
    "{feature}": ["wireless telemetry", "edge inference", "energy harvesting"],
    "{sensor_type}": ["EMG", "temperature", "strain", "pressure", "humidity", "ECG", "accelerometer"],
    "{platform}": ["UAV airframes", "soldier helmets", "vehicle hulls", "aircraft skins", "missile fins"],
    "{device}": ["MMIC", "MEMS sensor", "microcontroller", "power amplifier"],
    "{tech}": ["OLED", "QD-LED", "microLED"],
    "{ink_type}": ["silver nanoparticle", "copper nanoparticle", "carbon"],
    "{material}": ["silver", "copper", "carbon nanotube"],
    "{substrate}": ["Kapton HN", "PEN substrate", "TPU"],
    "{process}": ["aerosol jet printing", "screen printing", "inkjet printing"],
}


def fill_template(template, rng):
    s = template
    for key, options in PLACEHOLDERS.items():
        if key in s:
            s = s.replace(key, rng.choice(options))
    return s


def make_abstract(title, focus, materials, processes, pis, inst, rng):
    materials_phrase = " and ".join(materials[:2]) if materials else "advanced materials"
    process_phrase = f" using {processes[0]}" if processes else ""
    pi_str = pis[0] if pis else "the project team"
    metrics = rng.choice([
        "30-40% improvement in performance metrics",
        "TRL advancement from 4 to 6 over the program period",
        "demonstrated reliability across 500+ thermal cycles",
        "85/85 humidity test compliance per JEDEC standards",
        "consistent results across three independent process runs",
    ])
    return (
        f"This {focus.lower()} effort, led by {pi_str} at {inst}, "
        f"developed and characterized {materials_phrase}{process_phrase} "
        f"to advance the objectives outlined in the title. "
        f"Key results include {metrics}. "
        f"The project produced detailed materials and process characterization data "
        f"deposited into the NextFlex member knowledge base for cross-project reuse."
    )


def make_outcomes(rng):
    return rng.choice([
        "Demonstrated functional prototypes meeting all program objectives. "
        "Generated comprehensive characterization data. "
        "Identified pathways for follow-on commercialization.",
        "Delivered TRL-4 to TRL-6 demonstrators. "
        "Published 2-3 peer-reviewed papers and filed provisional patents.",
        "Achieved key technical milestones ahead of schedule. "
        "Transitioned process documentation to industry partners.",
        "Met or exceeded all program-level KPIs. Delivered final demonstrator units "
        "to the sponsor for independent evaluation.",
    ])


def make_chunks(project, materials, processes, perfs, rng):
    chunks = []
    pid = project["id"]
    pc = project["project_call"]
    inst = project["lead_institution"]

    chunks.append({"section": "abstract", "page": 1, "text": project["abstract"]})

    for i, mat in enumerate(materials[:3]):
        props = mat.get("properties", {})
        prop_str = ", ".join(f"{k}={v}" for k, v in list(props.items())[:3])
        chunks.append({
            "section": "materials",
            "page": 5 + i,
            "text": f"{mat['name']} was selected as the primary {mat['subtype']} for this study. "
                    f"Vendor specifications report {prop_str}. "
                    f"Material was deposited via {processes[0]['name'] if processes else 'standard'} "
                    f"and characterized for compatibility with the target {project['focus_area'].lower()} application.",
        })

    for i, proc in enumerate(processes[:2]):
        props = proc.get("properties", {})
        prop_str = ", ".join(f"{k}={v}" for k, v in list(props.items())[:4])
        chunks.append({
            "section": "process",
            "page": 10 + i,
            "text": f"The {proc['name']} process was operated at the following parameters: {prop_str}. "
                    f"Process optimization studies showed sensitivity to "
                    f"{rng.choice(['platen temperature', 'flow rate', 'dwell time', 'wavelength'])}.",
        })

    for i, perf in enumerate(perfs[:2]):
        props = perf.get("properties", {})
        prop_str = ", ".join(f"{k}={v}" for k, v in list(props.items())[:4])
        chunks.append({
            "section": "results",
            "page": 15 + i,
            "text": f"Measured {perf['name']} for the integrated demonstrator showed {prop_str}. "
                    f"Results compare favorably against published benchmarks for {project['focus_area'].lower()}. "
                    f"Statistical analysis across {rng.randint(3, 8)} independent samples confirms repeatability.",
        })

    if rng.random() > 0.3:
        chunks.append({
            "section": "reliability",
            "page": 20,
            "text": f"Reliability characterization included thermal cycling per IPC-9701 "
                    f"(-40C to +125C, {rng.choice([100, 250, 500, 1000])} cycles), "
                    f"humidity exposure per JEDEC JESD22-A101 (85C/85% RH, {rng.choice([168, 500, 1000])} hours), "
                    f"and mechanical flex testing.",
        })

    chunks.append({
        "section": "conclusions",
        "page": 25,
        "text": project["outcomes"] + f" The work was conducted at {inst} under NextFlex {pc}.",
    })

    for i, c in enumerate(chunks):
        c["id"] = f"{pid}-c{i:02d}"
        c["project_id"] = pid
    return chunks


def generate_corpus(rng):
    projects = []
    entities = {}
    relationships = []
    chunks = []
    deployments = []

    # Build the fixed entity pool
    for name, vendor, props in CONDUCTIVE_INKS:
        eid = f"mat-cond-{hashlib.md5(name.encode()).hexdigest()[:8]}"
        entities[eid] = {"id": eid, "type": "material", "subtype": "conductive_ink",
                          "name": name, "vendor": vendor, "properties": props,
                          "source_project_ids": [], "classification": "public"}
    for name, vendor, props in DIELECTRIC_INKS:
        eid = f"mat-diel-{hashlib.md5(name.encode()).hexdigest()[:8]}"
        cls = "member_share" if "BST" in name else "public"
        entities[eid] = {"id": eid, "type": "material", "subtype": "dielectric_ink",
                          "name": name, "vendor": vendor, "properties": props,
                          "source_project_ids": [], "classification": cls}
    for name, vendor, props in SUBSTRATES:
        eid = f"mat-subs-{hashlib.md5(name.encode()).hexdigest()[:8]}"
        entities[eid] = {"id": eid, "type": "material", "subtype": "substrate",
                          "name": name, "vendor": vendor, "properties": props,
                          "source_project_ids": [], "classification": "public"}
    for name, vendor, props in ACTIVE_COMPONENTS:
        eid = f"mat-actv-{hashlib.md5(name.encode()).hexdigest()[:8]}"
        cls = "mission_relevant" if "GaN" in name else "public"
        entities[eid] = {"id": eid, "type": "material", "subtype": "active_component",
                          "name": name, "vendor": vendor, "properties": props,
                          "source_project_ids": [], "classification": cls}
    for name, subtype, props in PROCESSES:
        eid = f"proc-{hashlib.md5(name.encode()).hexdigest()[:8]}"
        entities[eid] = {"id": eid, "type": "process", "subtype": subtype,
                          "name": name, "vendor": "", "properties": props,
                          "source_project_ids": [], "classification": "public"}

    cond_inks = [e for e in entities.values() if e["subtype"] == "conductive_ink"]
    diel_inks = [e for e in entities.values() if e["subtype"] == "dielectric_ink"]
    subs = [e for e in entities.values() if e["subtype"] == "substrate"]
    procs = [e for e in entities.values() if e["type"] == "process"]

    for pc, year, n in PC_DEFINITIONS:
        for i in range(1, n + 1):
            focus = rng.choice(FOCUS_AREAS)
            inst, district = rng.choice(LEAD_INSTITUTIONS)

            n_pis = rng.randint(1, 3)
            pis = [f"Dr. {rng.choice(PI_FIRST)} {rng.choice(PI_LAST)}" for _ in range(n_pis)]
            n_co = rng.randint(0, 2)
            co_pis = [f"Dr. {rng.choice(PI_FIRST)} {rng.choice(PI_LAST)}" for _ in range(n_co)]

            n_partners = rng.randint(1, 3)
            all_insts = [x[0] for x in LEAD_INSTITUTIONS if x[0] != inst]
            partners = rng.sample(all_insts, min(n_partners, len(all_insts)))

            n_mats = rng.randint(2, 4)
            project_materials = (rng.sample(cond_inks, 1) + rng.sample(subs, 1)
                                + rng.sample(diel_inks + cond_inks + subs, max(0, n_mats - 2)))
            project_processes = rng.sample(procs, rng.randint(1, 3))

            project_perfs = []
            for _ in range(rng.randint(1, 3)):
                perf_name, perf_subtype, ranges = rng.choice(PERF_TEMPLATES)
                perf_props = {}
                for k, v in ranges.items():
                    if isinstance(v, tuple):
                        perf_props[k] = round(rng.uniform(v[0], v[1]), 2)
                    else:
                        perf_props[k] = v
                eid = f"perf-{rng.randint(0, 10**9):09d}"
                pdef = {"id": eid, "type": "performance", "subtype": perf_subtype,
                        "name": perf_name, "vendor": "", "properties": perf_props,
                        "source_project_ids": [], "classification": "public"}
                entities[eid] = pdef
                project_perfs.append(pdef)

            template = rng.choice(TITLE_TEMPLATES[focus])
            title = fill_template(template, rng)

            duration = rng.choice([12, 15, 18])
            start_month = rng.randint(0, 8)
            start = date(year, 1, 1) + timedelta(days=start_month * 30)
            end = start + timedelta(days=duration * 30)

            funding = rng.choice([150000, 200000, 250000, 300000, 400000, 500000, 750000])

            today = date.today()
            status = "completed" if end < today else ("in-progress" if start < today else "planned")

            keywords = rng.sample(
                ["flexible", "printed", "wearable", "RF", "antenna", "sensor",
                 "additive", "polyimide", "silver", "copper", "5G", "DoD", "soldier",
                 "wireless", "conformal", "MMIC", "SoP", "reliability"],
                rng.randint(4, 7),
            )

            peo = None
            if "soldier" in title.lower() or "wearable" in focus.lower():
                peo = "PEO-Soldier"
            elif "phased array" in title.lower() or "RF" in focus:
                peo = "PEO-IEWS"
            elif "communication" in title.lower() or "5G" in title or "antenna" in focus.lower():
                peo = "PEO-C3T"

            classif = rng.choices(
                ["public", "member_share", "mission_relevant"],
                weights=[60, 25, 15],
            )[0]

            n_pubs = rng.randint(0, 4)
            publications = [
                f"Author et al., \"{title[:40]}...\", IEEE Trans. Components Packaging Manuf. Tech., "
                f"vol. {rng.randint(10, 14)}, no. {rng.randint(1, 12)}, "
                f"pp. {rng.randint(1, 999)}-{rng.randint(1000, 2000)}, {year + rng.randint(0, 2)}."
                for _ in range(n_pubs)
            ]
            n_patents = rng.randint(0, 2)
            patents = [
                f"US Patent Application #{rng.randint(16000000, 18999999)} ({year + rng.randint(0, 2)})"
                for _ in range(n_patents)
            ]

            project = {
                "id": f"NFX-{pc.replace(' ', '').replace('.', '_')}-{i:03d}",
                "project_call": pc, "title": title, "lead_institution": inst,
                "principal_investigators": pis, "co_investigators": co_pis,
                "industry_partners": partners,
                "start_date": start.isoformat(), "end_date": end.isoformat(),
                "funding_amount": funding, "abstract": "",
                "focus_area": focus,
                "materials_used": [m["name"] for m in project_materials],
                "processes_used": [p["name"] for p in project_processes],
                "outcomes": "", "status": status,
                "publications": publications, "patents": patents, "keywords": keywords,
                "congressional_district": district,
                "trl_start": rng.choice([3, 4, 5]),
                "trl_end": rng.choice([5, 6, 7]),
                "classification": classif, "peo": peo,
            }
            project["abstract"] = make_abstract(
                title, focus, project["materials_used"], project["processes_used"],
                pis, inst, rng,
            )
            project["outcomes"] = make_outcomes(rng)
            projects.append(project)

            for ent_list in (project_materials, project_processes, project_perfs):
                for ent in ent_list:
                    ent["source_project_ids"].append(project["id"])

            for p_ent in project_processes:
                for m_ent in project_materials:
                    relationships.append({
                        "from_id": p_ent["id"], "to_id": m_ent["id"],
                        "rel_type": "USES_MATERIAL",
                        "confidence": round(rng.uniform(0.8, 1.0), 2),
                        "source_project_id": project["id"],
                    })
            for p_ent in project_processes:
                for perf_ent in project_perfs:
                    relationships.append({
                        "from_id": p_ent["id"], "to_id": perf_ent["id"],
                        "rel_type": "RESULTS_IN",
                        "confidence": round(rng.uniform(0.7, 0.95), 2),
                        "source_project_id": project["id"],
                    })
            for m_ent in project_materials[:2]:
                for perf_ent in project_perfs[:1]:
                    relationships.append({
                        "from_id": m_ent["id"], "to_id": perf_ent["id"],
                        "rel_type": "AFFECTS",
                        "confidence": round(rng.uniform(0.6, 0.9), 2),
                        "source_project_id": project["id"],
                    })

            chunks.extend(make_chunks(project, project_materials, project_processes, project_perfs, rng))

    deploy_templates = [
        ("Optomec AJ5X production line - Ag nanoparticle traces", "Optomec Inc.", "production",
         "Commercial deployment at Optomec Albuquerque facility. AJ-printed Ag nanoparticle conductive traces on polyimide.",
         "AZ-01", "PEO-Soldier"),
        ("Raytheon RURI - printed BST phase shifters", "Raytheon Technologies", "pilot",
         "Pilot production of BST-based phase shifters using PERC/RURI aerosol jet process.",
         "MA-03", "PEO-IEWS"),
        ("Northrop Grumman - flexible sensor substrates", "Northrop Grumman", "qualification",
         "Advanced packaging reliability data for soldier-worn programs. Kapton HN + Cu ink.",
         "VA-10", "PEO-Soldier"),
        ("ANI / FlexTech - printed interconnects to bare die", "ANI Inc.", "evaluation",
         "FlexTech RFP project leveraging screen-printed interconnects.", "CA-17", None),
        ("DEVCOM C5ISR - tactical 5G printed antenna array", "Fort Liberty / DEVCOM", "field_eval",
         "Printed X-band patch antenna arrays for field evaluation.", "NC-07", "PEO-C3T"),
        ("Boeing R&T - structural health monitoring sensors", "Boeing R&T", "qualification",
         "Printed sensor networks for SHM on commercial and military aircraft.", "WA-09", "AFLCMC"),
        ("Lockheed Martin - conformal antenna prototype", "Lockheed Martin", "evaluation",
         "Lightweight conformal antennas for UAV airframes.", "MD-05", "PEO-IEWS"),
    ]
    for i, base in enumerate(deploy_templates):
        title, org, status, desc, district, peo = base
        candidates = [p for p in projects if p["lead_institution"] == org or org in p["industry_partners"]]
        sources = [p["id"] for p in rng.sample(candidates, min(3, len(candidates)))] if candidates else []
        deployments.append({
            "id": f"deploy-{i:03d}", "title": title, "organization": org, "status": status,
            "description": desc, "source_project_ids": sources,
            "district": district, "peo": peo,
            "deploy_date": "2024-{:02d}-15".format((i % 12) + 1),
        })
    for i in range(len(deploy_templates), 30):
        proj = rng.choice(projects)
        deployments.append({
            "id": f"deploy-{i:03d}",
            "title": f"{proj['lead_institution']} - {proj['focus_area']} pilot",
            "organization": proj["lead_institution"],
            "status": rng.choice(["evaluation", "pilot", "qualification"]),
            "description": f"Internal evaluation derived from {proj['project_call']}: {proj['title']}",
            "source_project_ids": [proj["id"]],
            "district": proj["congressional_district"],
            "peo": proj.get("peo"),
            "deploy_date": "2024-{:02d}-01".format((i % 12) + 1),
        })

    return {"projects": projects, "entities": list(entities.values()),
            "relationships": relationships, "chunks": chunks, "deployments": deployments}


def init_db(reset=False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    rng = random.Random(42)
    corpus = generate_corpus(rng)

    proj_cols = ["id", "project_call", "title", "lead_institution",
                 "principal_investigators", "co_investigators", "industry_partners",
                 "start_date", "end_date", "funding_amount", "abstract",
                 "focus_area", "materials_used", "processes_used", "outcomes",
                 "status", "publications", "patents", "keywords",
                 "congressional_district", "trl_start", "trl_end",
                 "classification", "peo"]
    for p in corpus["projects"]:
        for k in ("principal_investigators", "co_investigators", "industry_partners",
                  "materials_used", "processes_used", "publications", "patents", "keywords"):
            p[k] = json.dumps(p[k])
    placeholders = ", ".join(["?"] * len(proj_cols))
    conn.executemany(
        f"INSERT INTO projects ({', '.join(proj_cols)}) VALUES ({placeholders})",
        [tuple(p[c] for c in proj_cols) for p in corpus["projects"]],
    )

    for e in corpus["entities"]:
        conn.execute(
            "INSERT INTO entities (id, type, subtype, name, properties, source_project_ids, classification) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (e["id"], e["type"], e["subtype"], e["name"],
             json.dumps(e["properties"]), json.dumps(e["source_project_ids"]),
             e["classification"]),
        )

    conn.executemany(
        "INSERT INTO relationships (from_id, to_id, rel_type, confidence, source_project_id) VALUES (?, ?, ?, ?, ?)",
        [(r["from_id"], r["to_id"], r["rel_type"], r["confidence"], r["source_project_id"])
         for r in corpus["relationships"]],
    )

    for c in corpus["chunks"]:
        conn.execute(
            "INSERT INTO chunks (id, project_id, section, page, text, classification) VALUES (?, ?, ?, ?, ?, ?)",
            (c["id"], c["project_id"], c["section"], c["page"], c["text"], "public"),
        )

    conn.execute("INSERT INTO chunks_fts (id, text, project_id, section) SELECT id, text, project_id, section FROM chunks")

    for code, state, rep, party, orgs in DISTRICTS:
        conn.execute(
            "INSERT INTO districts (code, state, representative, party, notable_orgs) VALUES (?, ?, ?, ?, ?)",
            (code, state, rep, party, json.dumps(orgs)),
        )
    conn.execute("""
        UPDATE districts SET
            project_count = (SELECT COUNT(*) FROM projects WHERE projects.congressional_district = districts.code),
            total_funding = COALESCE((SELECT SUM(funding_amount) FROM projects WHERE projects.congressional_district = districts.code), 0)
    """)

    for code, name, full_name, location, relevance, offices, district in PEOS:
        n_active = len([p for p in corpus["projects"] if p.get("peo") == code])
        conn.execute(
            "INSERT INTO peos (code, name, full_name, location, relevance, program_offices, active_programs, district) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, name, full_name, location, relevance, json.dumps(offices), n_active, district),
        )

    for d in corpus["deployments"]:
        conn.execute(
            "INSERT INTO deployments (id, title, organization, status, description, source_project_ids, district, peo, deploy_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (d["id"], d["title"], d["organization"], d["status"], d["description"],
             json.dumps(d["source_project_ids"]), d["district"], d["peo"], d["deploy_date"]),
        )

    conn.execute("""
        INSERT INTO projects_fts (id, title, abstract, principal_investigators,
                                   lead_institution, materials_used, processes_used, keywords, focus_area)
        SELECT id, title, abstract, principal_investigators, lead_institution,
               materials_used, processes_used, keywords, focus_area
        FROM projects
    """)

    conn.commit()
    counts = {
        "projects": conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "relationships": conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
        "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "districts": conn.execute("SELECT COUNT(*) FROM districts").fetchone()[0],
        "deployments": conn.execute("SELECT COUNT(*) FROM deployments").fetchone()[0],
        "peos": conn.execute("SELECT COUNT(*) FROM peos").fetchone()[0],
    }
    funding = conn.execute("SELECT SUM(funding_amount) FROM projects").fetchone()[0]
    pcs = conn.execute("SELECT COUNT(DISTINCT project_call) FROM projects").fetchone()[0]
    db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    conn.close()

    print(f"DB initialized: {DB_PATH} ({db_size_mb:.1f} MB)")
    print(f"  {counts['projects']} projects, {pcs} PCs, ${funding:,} total")
    print(f"  {counts['entities']} entities, {counts['relationships']} relationships, {counts['chunks']} chunks")
    print(f"  {counts['districts']} districts, {counts['deployments']} deployments, {counts['peos']} PEOs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    init_db(reset=args.reset)
