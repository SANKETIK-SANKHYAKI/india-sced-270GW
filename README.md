# india-sced-270GW

**Security-Constrained Economic Dispatch (SCED) model of India's ISTS grid — 21 May 2026**

India broke its all-time electricity demand record on 21 May 2026: **270,820 MW at 15:45 IST.**

This repository contains a 5-region LP-based SCED model built to understand what happened inside the grid on that day — not from news headlines, but from the optimization mathematics that NLDC solves every 15 minutes.

---

## What this model does

Given every generator available and every transmission limit on 21 May 2026, the model finds:
- The **least-cost dispatch** across 5 ISTS regions (NR, WR, SR, ER, NER) for all 24 hours
- **Locational Marginal Prices (LMPs)** — shadow prices of the power balance constraint
- **Congestion prices** — shadow prices of binding TTC corridors
- **RE curtailment** — solar and wind spillage when corridors are full
- **Unserved demand** — load shedding when capacity + transmission cannot meet demand

---

## Key finding at peak hour (15:00)

| Region | LMP (Rs/MWh) | Interpretation |
|--------|-------------|----------------|
| WR | 3,300 | Surplus cheap coal — Sasan, Sipat, Lara running supercritical |
| NR | 10,000 (VOLL) | 15,600 MW gap; WR→NR HVDC at 99% capacity |
| SR | ~4,200 | Partially import-constrained |
| ER | ~3,500 | Coal surplus region |
| NER | ~4,800 | Isolated, gas-dependent |

**WR→NR price spread: ₹6,700/MWh** — this is not a market price. It is the shadow price of a saturated HVDC corridor. One cable being full.

Model reproduced **5.10 GW on WR→NR** vs **5.05 GW NLDC SCADA actual** — 99% match.

---

## Repository structure

```
india-sced-270GW/
│
├── model/
│   └── india_sced_v1.py          # GAMSpy LP model — main file
│
├── data/
│   ├── model_demand.csv          # 5-region hourly demand (MW), 24 hours
│   ├── model_gen_stack.csv       # Generator stack: Pmax, Pmin, variable cost
│   ├── model_re_profiles.csv     # Solar and wind availability profiles
│   ├── model_ttc.csv             # PGCIL TTC corridor limits (MW)
│   └── README_data.md            # Data sources and methodology
│
├── results/
│   ├── FINAL_LMP.csv             # Regional LMPs Rs/MWh, all 24 hours
│   ├── FINAL_dispatch.csv        # Generator dispatch MW by region/fuel/hour
│   ├── FINAL_flows.csv           # Inter-regional corridor flows MW
│   └── FINAL_congestion.csv      # Congestion shadow prices Rs/MWh
│
├── visuals/                      # Output charts and plots
├── requirements.txt
├── LICENSE
└── README.md
```

---

## How to run

### 1. Install dependencies

```bash
pip install gamspy pandas numpy
gamspy install solver highs
```

### 2. Set data path

In `model/india_sced_v1.py`, set:
```python
DATA = "path/to/your/data/folder"
```
Point it at the `data/` folder in this repo.

### 3. Run

```bash
python model/india_sced_v1.py
```

Results will be saved to the `data/` folder as `results_*.csv`.

---

## Model formulation

### Sets
| Symbol | Description |
|--------|-------------|
| R | 5 ISTS regions: NR, WR, SR, ER, NER |
| G | Fuel types: nuclear, hydro, coal, gas, solar, wind |
| T | Hours 1–24 |
| C ⊆ R×R | Directed transmission corridors |

### Variables
| Variable | Description |
|----------|-------------|
| P[r,g,t] | Dispatch (MW), ≥ 0 |
| FLOW[r,r',t] | Corridor flow (MW), free |
| CURT[r,t] | Solar curtailment (MW), ≥ 0 |
| CURT_W[r,t] | Wind curtailment (MW), ≥ 0 |
| UNS[r,t] | Unserved demand (MW), ≥ 0 |

### Objective
Minimize total system cost:

```
min  Σ(r,g,t) VC[r,g] · P[r,g,t]  +  Σ(r,t) VOLL · UNS[r,t]
```

VOLL = ₹10,000/MWh

### Constraints

**Power balance** (dual = LMP):
```
Σ_g P[r,g,t] + Σ_{r':(r',r)∈C} FLOW[r',r,t] - Σ_{r':(r,r')∈C} FLOW[r,r',t]
    = D[r,t] - UNS[r,t]    ∀ r,t
```

**Generation bounds:**
```
Pmin[r,g] ≤ P[r,g,t] ≤ Pmax[r,g]    ∀ r,g,t
```

**TTC limits** (dual = congestion price):
```
-TTC[r,r'] ≤ FLOW[r,r',t] ≤ TTC[r,r']    ∀ (r,r')∈C, t
```

**RE must-run with curtailment:**
```
P[r,"solar",t] + CURT[r,t]   = RE_solar[r,t]    ∀ r,t
P[r,"wind",t]  + CURT_W[r,t] = RE_wind[r,t]     ∀ r,t
```

---

## Data sources

| Data | Source |
|------|--------|
| Regional demand (24h) | NLDC PSP SCADA daily report, 21 May 2026 |
| Generator stack (Pmax, Pmin, VC) | CEA installed capacity report + CERC tariff orders |
| RE profiles | NLDC REMC VRE generation report, 21 May 2026 |
| TTC corridor limits | PGCIL TTC/ATC circular, May 2026 |
| Validation (SCADA flows) | NRLDC/WRLDC/ERLDC daily operation reports |

---

## Validation

| Metric | Model | Actual (SCADA) | Error |
|--------|-------|----------------|-------|
| WR→NR HVDC peak flow | 5,100 MW | 5,049 MW | +1.0% |
| Total unserved demand | ~520 MWh | ~2,219 MWh (Bihar) | — |
| Peak system demand served | 270,200 MW | 270,820 MW | -0.2% |

---

## Limitations and next steps

**Current limitations (v1):**
- No ramping constraints — each hour solved independently
- No unit commitment (binary on/off) — all generators assumed online
- Single TTC value per corridor — no directional asymmetry
- 5-region aggregation — intra-state congestion not captured

**Planned (v2):**
- Ramping constraints between consecutive hours
- Intra-state SCED for major states (UP, Maharashtra, Tamil Nadu)
- SCUC (unit commitment) as MIP extension
- PMU phase angle validation overlay

---

## Inspiration

Inspired by [Soonee Sushil Kumar Sir's post](https://lnkd.in/gDvUmBY5) on SCED and SMP plots.

> *"Wish every SLDC models the state SCED, causes economy and extracts the wisdom through marginals of every limiting constraint."*
> — Soonee Sushil Kumar, Former CEO POSOCO / Grid-India

---

## Author

**Surjeet Chauhan**
LinkedIn: [https://www.linkedin.com/in/clearsparks-surjeet/]

---

## License

MIT License — see [LICENSE](LICENSE) for details.
Free to use, modify, and share with attribution.
