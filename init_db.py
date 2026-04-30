"""
NextFlex Project Portal — Database initialization & seed data.

Generates a representative corpus of ~75 projects across NextFlex
Project Calls 1.0 through 10.0, based on publicly known focus areas
of the FHE manufacturing institute.

USAGE:
    python3 init_db.py           # creates nextflex.db and seeds it
    python3 init_db.py --reset   # drops + recreates from scratch

NOTE: This is demonstration data. Replace with your authoritative
NextFlex archive by importing CSV/JSON into the same schema.
"""

import argparse
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "nextflex.db"

SCHEMA = """
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS projects_fts;

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    project_call TEXT NOT NULL,
    title TEXT NOT NULL,
    lead_institution TEXT,
    principal_investigators TEXT,    -- JSON array
    co_investigators TEXT,           -- JSON array
    industry_partners TEXT,          -- JSON array
    start_date TEXT,
    end_date TEXT,
    funding_amount INTEGER,
    abstract TEXT,
    focus_area TEXT,
    materials_used TEXT,             -- JSON array
    processes_used TEXT,             -- JSON array
    outcomes TEXT,
    status TEXT,
    publications TEXT,               -- JSON array
    patents TEXT,                    -- JSON array
    keywords TEXT,                   -- JSON array
    congressional_district TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common filters
CREATE INDEX idx_pc ON projects (project_call);
CREATE INDEX idx_focus ON projects (focus_area);
CREATE INDEX idx_inst ON projects (lead_institution);
CREATE INDEX idx_status ON projects (status);

-- Full-text search
CREATE VIRTUAL TABLE projects_fts USING fts5(
    id UNINDEXED,
    title,
    abstract,
    principal_investigators,
    lead_institution,
    materials_used,
    processes_used,
    keywords,
    focus_area
);
"""


# ─── Realistic NextFlex topic seeds ───
FOCUS_AREAS = [
    "Flexible Circuits", "Printed RF/Antennas", "Wearable Sensors",
    "Conformal Electronics", "Hybrid Packaging", "Printed Power Devices",
    "Flexible Displays", "Materials & Inks", "Reliability & Test",
    "Manufacturing Processes", "Soldier-Worn Systems", "Medical Devices",
    "IoT Sensor Nodes", "Phased Array Antennas", "Tunable Substrates",
]

LEAD_INSTITUTIONS = [
    ("UMass Lowell", "MA-03"), ("American Semiconductor", "ID-02"),
    ("GE Aerospace", "OH-01"), ("Boeing R&T", "WA-09"),
    ("Northrop Grumman", "VA-10"), ("Raytheon Technologies", "CT-04"),
    ("Lockheed Martin", "MD-05"), ("Honeywell Aerospace", "AZ-04"),
    ("Optomec Inc.", "NM-01"), ("DuPont Electronics", "DE-AL"),
    ("Stanford University", "CA-16"), ("MIT Lincoln Lab", "MA-05"),
    ("Georgia Tech", "GA-05"), ("Purdue University", "IN-04"),
    ("UC Berkeley", "CA-12"), ("ASU FlexTech", "AZ-04"),
    ("Iowa State University", "IA-04"), ("Penn State ARL", "PA-15"),
    ("Brewer Science", "MO-08"), ("FlexTrate Technologies", "CA-26"),
    ("ANI Inc.", "CA-17"), ("Cornell University", "NY-19"),
    ("Henkel Corporation", "MN-05"), ("Lockheed Skunk Works", "CA-25"),
    ("Sandia National Labs", "NM-01"),
]

CONDUCTIVE_INKS = ["GenesINk PL1-120 Ag NP", "Electroninks CI-005 Cu",
                   "DuPont PE872 Ag flake", "Henkel Loctite ECI 1010",
                   "NovaCentrix Ag", "Sun Chemical CRSN2442"]
DIELECTRIC_INKS = ["BST sinterless dielectric", "Heraeus EL-P 5042",
                   "DuPont 5018 dielectric", "Asahi CR-18G-KF"]
SUBSTRATES = ["Kapton HN 25µm polyimide", "Kapton HN 50µm polyimide",
              "PEN substrate", "TPU flexible substrate",
              "PET 75µm", "Glass-PI laminate"]
PROCESSES = ["Aerosol jet printing", "Inkjet printing", "Screen printing",
             "Gravure printing", "Laser sintering 830nm", "Photonic flash sintering",
             "Thermal cure 150C", "UV cure 365nm", "Die attach Ag epoxy",
             "Wire bonding", "Anisotropic conductive film", "Reactive ion etching"]

PI_FIRST = ["Vinod", "Alkim", "Oshadha", "Mark", "Shashi", "Pradeep",
            "Ramesh", "John", "Sarah", "David", "Karen", "Michael",
            "Lisa", "Robert", "Ahmed", "Wei", "Priya", "Hassan",
            "Elena", "James", "Yuki", "Carlos", "Amelia", "Peter"]
PI_LAST = ["Vokkarane", "Akyurtlu", "Ranasingha", "Allen", "Pal",
           "Kumar", "Patel", "Smith", "Johnson", "Chen", "Williams",
           "Brown", "Davis", "Garcia", "Miller", "Wilson", "Anderson",
           "Taylor", "Thomas", "Moore", "Martin", "Jackson", "Lee", "Park"]

# Project Call structure: roughly chronological
# Maps PC label → (year, quarter, num_projects)
PC_DEFINITIONS = [
    ("PC 1.0",  2017,  3), ("PC 1.1",  2017,  4), ("PC 1.2",  2017,  5),
    ("PC 2.0",  2018,  4), ("PC 2.6",  2018,  5),
    ("PC 3.0",  2019,  5), ("PC 3.5",  2019,  4),
    ("PC 4.0",  2019,  4), ("PC 4.5",  2020,  5),
    ("PC 5.0",  2020,  5), ("PC 5.6",  2020,  4),
    ("PC 6.0",  2020,  5), ("PC 6.9",  2021,  5),
    ("PC 7.0",  2021,  4), ("PC 7.1",  2021,  4),
    ("PC 8.0",  2022,  6), ("PC 8.5",  2022,  4),
    ("PC 9.0",  2022,  5), ("PC 9.5",  2023,  4), ("PC 9.6",  2023,  4),
    ("PC 10.0", 2023,  5), ("PC 10.2", 2024,  4),
]

TITLE_TEMPLATES = {
    "Flexible Circuits": [
        "Multi-layer Flexible Interconnect Demonstrators for {app}",
        "High-Density Flex Circuit Architectures for {app}",
        "Reliability Characterization of Flexible Substrates in {env} Environments",
    ],
    "Printed RF/Antennas": [
        "Conformal {band} Antenna Array on Flexible Substrates",
        "Printed {component} for {band} Communications",
        "Beam-Steerable {band} Phased Array Using Aerosol Jet Printing",
    ],
    "Wearable Sensors": [
        "Stretchable Strain Sensor for {app} Monitoring",
        "Skin-Conformal Biosensor Array with {feature}",
        "Wireless {sensor_type} Sensor Patch for Continuous Monitoring",
    ],
    "Conformal Electronics": [
        "Conformal Electronic Skin for {app}",
        "Curved-Surface Electronics Integration for {platform}",
    ],
    "Hybrid Packaging": [
        "Advanced Hybrid Packaging for {device} Integration",
        "Fan-Out Wafer-Level Packaging on Flexible Substrate",
        "Die Attach Reliability for Flexible Hybrid Electronics",
    ],
    "Printed Power Devices": [
        "Printed Energy Storage for {app}",
        "Flexible Power Management IC Integration",
    ],
    "Flexible Displays": [
        "Foldable {tech} Display Backplane",
        "High-Resolution Printed Display Driver Circuit",
    ],
    "Materials & Inks": [
        "Novel {ink_type} Ink Formulation for Extreme Environment Reliability",
        "Low-Temperature Sintering of {material} Conductive Inks",
        "BST Dielectric Nano-Ink for {band} Tunable Substrates",
    ],
    "Reliability & Test": [
        "Accelerated Life Testing of Printed Conductors on {substrate}",
        "Failure Mode Analysis of Flexible Hybrid Assemblies",
    ],
    "Manufacturing Processes": [
        "High-Volume Aerosol Jet Manufacturing Process Development",
        "Roll-to-Roll Integration of Hybrid Components",
        "Process Optimization for {process} on Polyimide",
    ],
    "Soldier-Worn Systems": [
        "Body-Worn {sensor_type} Array for Soldier Lethality",
        "Lightweight Conformal Antenna for Dismounted Communications",
    ],
    "Medical Devices": [
        "Implantable Flexible Sensor for {app} Monitoring",
        "Wearable ECG Patch with {feature}",
    ],
    "IoT Sensor Nodes": [
        "Self-Powered IoT Node with Printed {sensor_type} Sensor",
        "Energy-Harvesting Wireless Sensor Node",
    ],
    "Phased Array Antennas": [
        "Printed {band} Phased Array with PLTL-BST Phase Shifters",
        "Conformal {band} Beamforming Array",
    ],
    "Tunable Substrates": [
        "Voltage-Tunable BST Substrate for {band} RF Applications",
        "Reconfigurable RF Substrate with Sinterless Dielectric Inks",
    ],
}

PLACEHOLDERS = {
    "{app}": ["health monitoring", "structural health monitoring", "asset tracking",
              "rehabilitation", "industrial automation", "vehicle telemetry"],
    "{env}": ["high-temperature", "high-vibration", "humidity-cycled", "saline"],
    "{band}": ["X-band", "Ku-band", "Ka-band", "S-band", "5G mm-wave", "L-band"],
    "{component}": ["filter", "phase shifter", "switch matrix", "bandpass filter"],
    "{feature}": ["wireless telemetry", "edge inference", "energy harvesting"],
    "{sensor_type}": ["EMG", "temperature", "strain", "pressure", "humidity", "ECG"],
    "{platform}": ["UAV airframes", "soldier helmets", "vehicle hulls", "aircraft skins"],
    "{device}": ["MMIC", "MEMS sensor", "microcontroller", "power amplifier"],
    "{tech}": ["OLED", "QD-LED", "microLED"],
    "{ink_type}": ["silver nanoparticle", "copper nanoparticle", "carbon"],
    "{material}": ["silver", "copper", "carbon nanotube"],
    "{substrate}": ["Kapton HN", "PEN substrate", "TPU"],
    "{process}": ["aerosol jet printing", "screen printing", "inkjet printing"],
}


def fill_template(template: str) -> str:
    s = template
    for key, options in PLACEHOLDERS.items():
        if key in s:
            s = s.replace(key, random.choice(options))
    return s


def make_abstract(title: str, focus: str, materials: list, processes: list, pis: list, inst: str) -> str:
    """Generate a plausible abstract."""
    materials_phrase = " and ".join(materials[:2]) if materials else "advanced materials"
    process_phrase = " with " + processes[0] if processes else ""
    pi_str = pis[0] if pis else "the project team"

    return (
        f"This {focus.lower()} project, led by {pi_str} at {inst}, "
        f"developed and characterized {materials_phrase}{process_phrase} "
        f"to achieve the objectives outlined in the title. "
        f"Outcomes included measurable improvements in performance metrics "
        f"and successful demonstration of the integrated system. "
        f"The project advanced TRL by 1-2 levels from the start to end of performance, "
        f"and produced data deposited into the NextFlex member knowledge base for "
        f"cross-project use."
    )


def make_outcomes(focus: str) -> str:
    """Generate a plausible outcomes summary."""
    options = [
        "Demonstrated functional prototypes meeting all program objectives. "
        "Generated detailed materials and process characterization data. "
        "Identified pathways for follow-on commercialization.",
        "Delivered TRL-4 to TRL-6 demonstrators. "
        "Published 2-3 peer-reviewed papers and filed provisional patent applications. "
        "Established baseline performance metrics for downstream programs.",
        "Achieved key technical milestones ahead of schedule. "
        "Transitioned process documentation to industry partners. "
        "Identified scaling considerations for high-volume manufacturing.",
    ]
    return random.choice(options)


def random_date(year: int, month_offset: int = 0) -> str:
    start = date(year, 1, 1) + timedelta(days=month_offset * 30)
    return start.isoformat()


def generate_projects() -> list[dict]:
    """Generate the full corpus."""
    random.seed(42)  # reproducible
    projects = []
    counter = 0

    for pc, year, n in PC_DEFINITIONS:
        for i in range(1, n + 1):
            counter += 1
            focus = random.choice(FOCUS_AREAS)
            inst, district = random.choice(LEAD_INSTITUTIONS)

            n_pis = random.randint(1, 3)
            pis = [f"Dr. {random.choice(PI_FIRST)} {random.choice(PI_LAST)}" for _ in range(n_pis)]
            n_co = random.randint(0, 2)
            co_pis = [f"Dr. {random.choice(PI_FIRST)} {random.choice(PI_LAST)}" for _ in range(n_co)]

            n_partners = random.randint(1, 3)
            all_insts = [i[0] for i in LEAD_INSTITUTIONS if i[0] != inst]
            partners = random.sample(all_insts, min(n_partners, len(all_insts)))

            n_materials = random.randint(2, 4)
            materials_pool = CONDUCTIVE_INKS + DIELECTRIC_INKS + SUBSTRATES
            materials = random.sample(materials_pool, n_materials)

            n_processes = random.randint(1, 3)
            processes = random.sample(PROCESSES, n_processes)

            template = random.choice(TITLE_TEMPLATES[focus])
            title = fill_template(template)

            duration = random.choice([12, 15, 18])
            start_month = random.randint(0, 8)
            start = date(year, 1, 1) + timedelta(days=start_month * 30)
            end = start + timedelta(days=duration * 30)

            funding = random.choice([150000, 200000, 250000, 300000, 400000, 500000, 750000])

            today = date.today()
            status = "completed" if end < today else ("in-progress" if start < today else "planned")

            keywords = random.sample(
                ["flexible", "printed", "wearable", "RF", "antenna", "sensor",
                 "additive", "polyimide", "silver", "copper", "5G", "DoD", "soldier",
                 "wireless", "conformal", "MMIC", "SoP", "reliability"],
                random.randint(4, 7),
            )

            n_pubs = random.randint(0, 4)
            publications = [
                f"Author et al., \"{title[:40]}...\", IEEE Trans. Components Packaging Manuf. Tech., "
                f"vol. {random.randint(10, 14)}, no. {random.randint(1, 12)}, pp. {random.randint(1, 999)}-{random.randint(1000, 2000)}, {year + random.randint(0, 2)}."
                for _ in range(n_pubs)
            ]

            n_patents = random.randint(0, 2)
            patents = [
                f"US Patent Application #{random.randint(16000000, 18999999)} "
                f"({year + random.randint(0, 2)})"
                for _ in range(n_patents)
            ]

            project = {
                "id": f"NFX-{pc.replace(' ', '').replace('.', '_')}-{i:03d}",
                "project_call": pc,
                "title": title,
                "lead_institution": inst,
                "principal_investigators": json.dumps(pis),
                "co_investigators": json.dumps(co_pis),
                "industry_partners": json.dumps(partners),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "funding_amount": funding,
                "abstract": make_abstract(title, focus, materials, processes, pis, inst),
                "focus_area": focus,
                "materials_used": json.dumps(materials),
                "processes_used": json.dumps(processes),
                "outcomes": make_outcomes(focus),
                "status": status,
                "publications": json.dumps(publications),
                "patents": json.dumps(patents),
                "keywords": json.dumps(keywords),
                "congressional_district": district,
            }
            projects.append(project)

    return projects


def init_db(reset: bool = False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    projects = generate_projects()

    cols = list(projects[0].keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO projects ({', '.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(p[c] for c in cols) for p in projects])

    # Build the FTS index
    conn.execute("""
        INSERT INTO projects_fts (id, title, abstract, principal_investigators,
                                  lead_institution, materials_used, processes_used,
                                  keywords, focus_area)
        SELECT id, title, abstract, principal_investigators,
               lead_institution, materials_used, processes_used,
               keywords, focus_area
        FROM projects
    """)

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    fts_count = conn.execute("SELECT COUNT(*) FROM projects_fts").fetchone()[0]
    pcs = conn.execute("SELECT DISTINCT project_call FROM projects ORDER BY project_call").fetchall()
    funding = conn.execute("SELECT SUM(funding_amount) FROM projects").fetchone()[0]
    conn.close()

    print(f"✓ Database initialized: {DB_PATH}")
    print(f"  {count} projects loaded")
    print(f"  {fts_count} FTS entries indexed")
    print(f"  {len(pcs)} project calls: {', '.join(p[0] for p in pcs)}")
    print(f"  Total funding represented: ${funding:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Drop and recreate")
    args = parser.parse_args()
    init_db(reset=args.reset)
