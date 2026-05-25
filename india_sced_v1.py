"""
India 5-Region SCED Model v1 — GAMSpy LP
21 May 2026 | Surjeet Chauhan
"""
import pandas as pd
import numpy as np
from gamspy import (Container, Set, Alias, Parameter, Variable,
                    Equation, Model, Sum, Sense, Options)

DATA = "/home/claude/sced_data"
print("="*60)
print("INDIA 5-REGION SCED — 21 MAY 2026  |  GAMSpy LP")
print("="*60)

# ── 1. RAW DATA ───────────────────────────────────────────
df_dem = pd.read_csv(f"{DATA}/model_demand.csv")
df_gen = pd.read_csv(f"{DATA}/model_gen_stack.csv")
df_re  = pd.read_csv(f"{DATA}/model_re_profiles.csv")
df_ttc = pd.read_csv(f"{DATA}/model_ttc.csv")

REGIONS = ['NR','WR','SR','ER','NER']
FUELS   = ['nuclear','hydro','coal','gas','solar','wind']
HOURS   = [str(h) for h in range(1,25)]
VOLL    = 10000   # Rs/MWh

# ── 2. PARAMETER DICTS ────────────────────────────────────
D    = {(r, str(t)): float(df_dem.loc[df_dem.hour==t, r].values[0])
        for r in REGIONS for t in range(1,25)}

Pmax = {(r['region'], r['fuel']): float(r['Pmax_MW'])  for _, r in df_gen.iterrows()}
Pmin = {(r['region'], r['fuel']): float(r['Pmin_MW'])  for _, r in df_gen.iterrows()}
VC   = {(r['region'], r['fuel']): float(r['VarCost_Rs_kWh'])*1000 for _, r in df_gen.iterrows()}

RE_solar = {(r, str(t)): float(df_re.loc[df_re.hour==t, f"{r}_solar"].values[0])
             for r in REGIONS for t in range(1,25)}
RE_wind  = {(r, str(t)): float(df_re.loc[df_re.hour==t, f"{r}_wind"].values[0])
             for r in REGIONS for t in range(1,25)}

TTC_data = {(r['from_r'], r['to_r']): float(r['TTC_MW']) for _, r in df_ttc.iterrows()}
CORR = list(TTC_data.keys())

print(f"\nData loaded: {len(REGIONS)} regions, {len(FUELS)} fuels, 24 hours, {len(CORR)} corridors")

# ── 3. GAMSPY CONTAINER ───────────────────────────────────
m = Container()

R  = Set(m, "R",  records=REGIONS,   description="ISTS regions")
RP = Alias(m, "RP", alias_with=R)    # from-region alias for flow indexing
G  = Set(m, "G",  records=FUELS,     description="Fuel types")
T  = Set(m, "T",  records=HOURS,     description="Hours 1-24")
C  = Set(m, "C",  domain=[RP,R], records=CORR, description="Directed corridors")

# Parameters
p_D   = Parameter(m, "p_D",   domain=[R,T],    records=[(k[0],k[1],v) for k,v in D.items()])
p_max = Parameter(m, "p_max", domain=[R,G],    records=[(k[0],k[1],v) for k,v in Pmax.items()])
p_min = Parameter(m, "p_min", domain=[R,G],    records=[(k[0],k[1],v) for k,v in Pmin.items()])
p_vc  = Parameter(m, "p_vc",  domain=[R,G],    records=[(k[0],k[1],v) for k,v in VC.items()])
p_sol = Parameter(m, "p_sol", domain=[R,T],    records=[(k[0],k[1],v) for k,v in RE_solar.items()])
p_wnd = Parameter(m, "p_wnd", domain=[R,T],    records=[(k[0],k[1],v) for k,v in RE_wind.items()])
p_ttc = Parameter(m, "p_ttc", domain=[RP,R],   records=[(k[0],k[1],v) for k,v in TTC_data.items()])

print("Parameters defined ✓")

# Variables
P    = Variable(m, "P",    domain=[R,G,T],  type="positive", description="Dispatch MW")
FLOW = Variable(m, "FLOW", domain=[RP,R,T], type="free",     description="Corridor flow MW")
CURT = Variable(m, "CURT", domain=[R,T],    type="positive", description="RE curtailment MW")
UNS  = Variable(m, "UNS",  domain=[R,T],    type="positive", description="Unserved demand MW")

print("Variables defined ✓")

# ── 4. EQUATIONS ──────────────────────────────────────────
# EQ1: Power balance — dual = LMP (Rs/MWh)
eq_bal = Equation(m, "eq_bal", domain=[R,T],
                  description="Power balance (dual=LMP)")
eq_bal[R,T] = (
    Sum(G, P[R,G,T])
    + Sum(RP.where[C[RP,R]], FLOW[RP,R,T])   # imports
    - Sum(RP.where[C[R,RP]], FLOW[R,RP,T])   # exports
    == p_D[R,T] - UNS[R,T]
)

# EQ2/3: Generation bounds
eq_ub = Equation(m, "eq_ub", domain=[R,G,T])
eq_ub[R,G,T] = P[R,G,T] <= p_max[R,G]

eq_lb = Equation(m, "eq_lb", domain=[R,G,T])
eq_lb[R,G,T] = P[R,G,T] >= p_min[R,G]

# EQ4/5: TTC limits — dual = congestion price (Rs/MWh)
eq_tc_up = Equation(m, "eq_tc_up", domain=[RP,R,T],
                    description="TTC upper limit (dual=congestion cost)")
eq_tc_up[C[RP,R],T] = FLOW[RP,R,T] <= p_ttc[RP,R]

eq_tc_lo = Equation(m, "eq_tc_lo", domain=[RP,R,T])
eq_tc_lo[C[RP,R],T] = FLOW[RP,R,T] >= -p_ttc[RP,R]

# EQ6/7: RE must-run with curtailment slack
eq_sol = Equation(m, "eq_sol", domain=[R,T],
                  description="Solar: dispatch + curtailment = available")
eq_sol[R,T] = P[R,"solar",T] + CURT[R,T] == p_sol[R,T]

# Separate wind curtailment variable
CURT_W = Variable(m, "CURT_W", domain=[R,T], type="positive",
                  description="Wind curtailment MW")
eq_wnd = Equation(m, "eq_wnd", domain=[R,T],
                  description="Wind: dispatch + curtailment = available")
eq_wnd[R,T] = P[R,"wind",T] + CURT_W[R,T] == p_wnd[R,T]

print("Equations defined ✓")

# ── 5. OBJECTIVE ──────────────────────────────────────────
obj = (Sum([R,G,T], p_vc[R,G] * P[R,G,T])
       + Sum([R,T], VOLL * UNS[R,T]))

sced = Model(m, name="SCED_V1",
             equations=m.getEquations(),
             problem="LP",
             sense=Sense.MIN,
             objective=obj)

print("Model assembled ✓")

# ── 6. SOLVE ──────────────────────────────────────────────
print("\nSolving...")
sced.solve()

print(f"\nStatus    : {sced.status}")
print(f"Obj (Rs)  : {sced.objective_value:,.0f}  (total 24-hour system cost)")
avg_lmp_approx = sced.objective_value / (sum(D.values()) * 1) if sum(D.values()) > 0 else 0

# ── 7. EXTRACT & SAVE RESULTS ─────────────────────────────
print("\nExtracting results...")

def save(df, name):
    if df is not None and not df.empty:
        df.to_csv(f"{DATA}/results_{name}.csv", index=False)
        print(f"  ✓ results_{name}.csv  ({len(df)} rows)")
    else:
        print(f"  ✗ {name} — empty")

save(P.records,      "dispatch")
save(FLOW.records,   "flows")
save(CURT.records,   "curtailment_solar")
save(CURT_W.records, "curtailment_wind")
save(UNS.records,    "unserved")
save(eq_bal.records, "LMP")
save(eq_tc_up.records,"congestion")

# ── 8. PRINT KEY RESULTS ──────────────────────────────────
print("\n" + "="*60)
print("RESULTS SUMMARY")
print("="*60)

# LMPs
lmp_df = eq_bal.records
if lmp_df is not None and not lmp_df.empty:
    lmp_df.columns = ['region','hour','level','marginal','lower','upper','scale']
    lmp_df['hour_int'] = pd.to_numeric(lmp_df['hour'], errors='coerce')
    lmp_df['LMP'] = pd.to_numeric(lmp_df['marginal'], errors='coerce').abs()
    
    pivot = lmp_df.pivot_table(index='hour_int', columns='region', values='LMP')
    pivot = pivot.sort_index()
    
    print("\n── Regional LMPs Rs/MWh (shadow price of power balance) ──")
    print(f"{'Hr':>3} {'NR':>7} {'WR':>7} {'SR':>7} {'ER':>7} {'NER':>7}  SR-WR_spread")
    for h in range(1,25):
        if h in pivot.index:
            row = pivot.loc[h]
            nr  = row.get('NR', 0)  or 0
            wr  = row.get('WR', 0)  or 0
            sr  = row.get('SR', 0)  or 0
            er  = row.get('ER', 0)  or 0
            ner = row.get('NER',0)  or 0
            spread = sr - wr
            mark = " ◄ PEAK" if h == 16 else ""
            print(f"{h:>3} {nr:>7.1f} {wr:>7.1f} {sr:>7.1f} {er:>7.1f} {ner:>7.1f}  {spread:>+7.1f}{mark}")

# Congestion
con_df = eq_tc_up.records
if con_df is not None and not con_df.empty:
    con_df.columns = ['from_r','to_r','hour','level','marginal','lower','upper','scale']
    con_df['congestion'] = pd.to_numeric(con_df['marginal'], errors='coerce').abs()
    con_df['hour_int'] = pd.to_numeric(con_df['hour'], errors='coerce')
    
    print("\n── Congestion shadow prices Rs/MWh (binding corridors) ──")
    binding = con_df[con_df['congestion'] > 1].groupby(['from_r','to_r'])['congestion'].agg(['mean','max','count'])
    if not binding.empty:
        for idx, row in binding.iterrows():
            print(f"  {idx[0]}→{idx[1]}: avg {row['mean']:,.0f} Rs/MWh | "
                  f"max {row['max']:,.0f} Rs/MWh | binding {row['count']} hours")
    else:
        print("  No significantly binding corridors (all flows within TTC)")

# Dispatch totals
p_df = P.records
if p_df is not None and not p_df.empty:
    p_df.columns = ['region','fuel','hour','level','marginal','lower','upper','scale']
    p_df['MW'] = pd.to_numeric(p_df['level'], errors='coerce').fillna(0)
    p_df['MU'] = p_df['MW'] / 1000  # MWh per hour = MU per hour

    daily = p_df.groupby(['region','fuel'])['MU'].sum().reset_index()
    daily.columns = ['region','fuel','model_MU']

    actual = {
        ('NR','coal'):998,('NR','hydro'):292,('NR','nuclear'):49,('NR','gas'):25,
        ('NR','solar'):266,('NR','wind'):11,
        ('WR','coal'):1566,('WR','hydro'):61,('WR','nuclear'):60,('WR','gas'):53,
        ('WR','solar'):268,('WR','wind'):156,
        ('SR','coal'):836,('SR','hydro'):81,('SR','nuclear'):70,('SR','gas'):3,
        ('SR','solar'):171,('SR','wind'):171,
        ('ER','coal'):810,('ER','hydro'):51,('ER','solar'):8,
        ('NER','coal'):14,('NER','hydro'):29,('NER','gas'):19,
    }

    print("\n── Dispatch validation vs SCADA actuals ──")
    print(f"{'Region':<6} {'Fuel':<9} {'Model MU':>9} {'Actual MU':>10} {'Diff%':>7}")
    print("-"*46)
    for _, row in daily[daily['model_MU']>5].sort_values(['region','fuel']).iterrows():
        act = actual.get((row['region'], row['fuel']))
        if act:
            diff = (row['model_MU'] - act) / act * 100
            flag = "✓" if abs(diff)<20 else "⚠"
            print(f"{row['region']:<6} {row['fuel']:<9} {row['model_MU']:>9.1f} "
                  f"{act:>10.0f} {diff:>+6.1f}% {flag}")

# Unserved demand
uns_df = UNS.records
if uns_df is not None and not uns_df.empty:
    uns_df.columns = ['region','hour','level','marginal','lower','upper','scale']
    uns_df['MW'] = pd.to_numeric(uns_df['level'], errors='coerce').fillna(0)
    total = uns_df['MW'].sum()
    if total > 0:
        print(f"\n⚠ Unserved demand: {total:,.0f} MWh total")
        by_r = uns_df[uns_df['MW']>0].groupby('region')['MW'].sum()
        for r, mwh in by_r.items():
            print(f"   {r}: {mwh:,.0f} MWh  (actual Bihar: 2,219 MWh)")
    else:
        print(f"\n✓ All demand served within TTC and capacity constraints")

# RE curtailment
cu_df = CURT.records
if cu_df is not None and not cu_df.empty:
    cu_df.columns = ['region','hour','level','marginal','lower','upper','scale']
    cu_df['MW'] = pd.to_numeric(cu_df['level'], errors='coerce').fillna(0)
    total_curt = cu_df['MW'].sum()
    if total_curt > 0:
        print(f"\n⚡ Solar curtailment: {total_curt:,.0f} MWh total")
        print(f"   (WR Gujarat actual curtailment: 855 MWh)")

print("\n" + "="*60)
print("v1 MODEL COMPLETE")
print(f"All results in: {DATA}/results_*.csv")
print("="*60)
