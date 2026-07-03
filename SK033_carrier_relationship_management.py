#!/usr/bin/env python3
"""
SK033_carrier_relationship_management.py
========================================
Structured-state exporter for the "carrier-relationship-management" skill (SK033).

Same spirit as collect_motion_state.py: dump the FACTS you need to judge carrier
health BEFORE you trust a dashboard summary. It emits a carrier roster, per-carrier
performance KPIs, contract/relationship facts, weekly samples across a lookback
window, and SLA / cost / capacity / claims / contract diagnostics as "findings".

This is a SIMULATED skill: it generates realistic synthetic data and touches no
real systems, networks, or credentials -- the only file it writes is the JSON out.
Synthetic data is DETERMINISTIC for a given --seed, so runs are reproducible.

Runs on plain Python 3 (stdlib only), so it works straight from VS Code:

    python3 SK033_carrier_relationship_management.py \
        --out carrier_state.json --carriers 12 --lookback 12 --seed 33

Sub-Agent: SubAgent_33 (AG33)   Owner: Tarun
"""

import json
import random
import argparse
from datetime import datetime, timedelta


# ----------------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Export carrier relationship state to JSON.")
    p.add_argument("--out", default="carrier_state.json", help="Output JSON path")
    p.add_argument("--carriers", type=int, default=10, help="How many carriers to model")
    p.add_argument("--lookback", type=int, default=12,
                   help="Weeks of history to sample per carrier")
    p.add_argument("--seed", type=int, default=33,
                   help="RNG seed for reproducible synthetic data")
    p.add_argument("--ontime-target", type=float, default=0.95,
                   help="On-time delivery SLA target (fraction)")
    p.add_argument("--accept-target", type=float, default=0.90,
                   help="Tender acceptance SLA target (fraction)")
    p.add_argument("--claims-limit", type=float, default=0.02,
                   help="Claims ratio flagged above this (fraction of shipments)")
    p.add_argument("--cost-drift", type=float, default=0.08,
                   help="Recent cost-per-mile drift vs baseline flagged above this")
    p.add_argument("--volume-shortfall", type=float, default=0.15,
                   help="Recent volume below commitment by this fraction is flagged")
    p.add_argument("--contract-warn", type=int, default=45,
                   help="Warn when a contract expires within N days")
    return p.parse_args()


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def pct(x, n=4):
    return round(float(x), n)

def money(x, n=2):
    return round(float(x), n)

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

def stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5

def slope(xs):
    """Least-squares slope of xs vs their index (per-week trend)."""
    n = len(xs)
    if n < 2:
        return 0.0
    idx = list(range(n))
    mx, my = mean(idx), mean(xs)
    num = sum((idx[i] - mx) * (xs[i] - my) for i in range(n))
    den = sum((idx[i] - mx) ** 2 for i in range(n))
    return num / den if den else 0.0

def severity(ratio):
    """Map a 'how far past the threshold' ratio to a coarse severity label."""
    if ratio >= 0.50:
        return "critical"
    if ratio >= 0.20:
        return "high"
    return "moderate"


# ----------------------------------------------------------------------------
# Domain vocabulary (the synthetic universe the skill reasons about)
# ----------------------------------------------------------------------------

CARRIER_POOL = [
    "Ironclad Freight", "BlueLane Logistics", "Meridian Cartage", "Northwind Haulage",
    "Summit Line Transport", "Cedar Point Carriers", "Harbor & Rail Co", "Vanguard Drayage",
    "Redwood Freightways", "Atlas Overland", "Sable Ridge Logistics", "Copperline Transit",
    "Granite State Cartage", "Delta Fleet Systems", "Keystone Freight", "Anchor Intermodal",
]

SERVICE_TYPES = ["FTL", "LTL", "Intermodal", "Parcel", "Drayage"]
REGIONS = ["Midwest", "Northeast", "Southeast", "West", "Gulf", "Mountain"]
TIERS = ["strategic", "preferred", "transactional"]


# ----------------------------------------------------------------------------
# Step 1: carrier roster (the inventory)
# ----------------------------------------------------------------------------

def build_roster(rng, args, as_of):
    roster = []
    for i in range(args.carriers):
        name = (CARRIER_POOL[i] if i < len(CARRIER_POOL)
                else f"Carrier {i + 1:02d}")
        tier = rng.choices(TIERS, weights=[2, 3, 5])[0]
        # A hidden quality factor drives every downstream metric so that "good"
        # and "problem" carriers stay internally consistent across the samples.
        quality = clamp(rng.gauss(0.86, 0.09), 0.55, 0.995)
        trend = rng.uniform(-0.006, 0.004)  # weekly drift in on-time rate

        start_days = rng.randint(200, 900)
        term_days = rng.choice([180, 365, 540, 730])
        today = as_of.date()
        contract_start = today - timedelta(days=start_days)
        contract_end = contract_start + timedelta(
            days=((start_days // term_days) + 1) * term_days
        )

        roster.append({
            "id": f"CAR-{i + 1:03d}",
            "name": name,
            "tier": tier,
            "primary_service": rng.choice(SERVICE_TYPES),
            "regions": sorted(rng.sample(REGIONS, rng.randint(1, 3))),
            "lanes_covered": rng.randint(3, 40),
            "committed_weekly_volume": rng.choice([50, 75, 100, 150, 200, 300]),
            "baseline_cost_per_mile": money(rng.uniform(1.75, 3.40)),
            "contract_start": contract_start.isoformat(),
            "contract_end": contract_end.isoformat(),
            "days_to_expiry": (contract_end - today).days,
            # carried internally, not part of the public record:
            "_quality": quality,
            "_trend": trend,
        })
    return roster


# ----------------------------------------------------------------------------
# Step 2: weekly samples per carrier (the motion of the relationship)
# ----------------------------------------------------------------------------

def sample_weeks(rng, carrier, args, as_of):
    weeks = []
    q = carrier["_quality"]
    trend = carrier["_trend"]
    base_cpm = carrier["baseline_cost_per_mile"]
    commit = carrier["committed_weekly_volume"]

    for w in range(args.lookback):
        week_start = as_of - timedelta(weeks=(args.lookback - w))
        drift = trend * w
        on_time = clamp(rng.gauss(q + drift, 0.03), 0.60, 0.999)
        accept = clamp(rng.gauss(q + 0.02 + drift, 0.04), 0.55, 0.999)
        shipments = max(1, int(rng.gauss(commit * (0.85 + 0.25 * q), commit * 0.12)))
        claims = sum(1 for _ in range(shipments) if rng.random() < (0.03 * (1 - q)))
        cpm = money(base_cpm * rng.gauss(1.0 + 0.10 * (1 - q), 0.05))
        transit = round(rng.gauss(34 - 8 * q, 4), 1)
        utilization = clamp(rng.gauss(0.70 + 0.25 * q, 0.08), 0.30, 1.0)

        weeks.append({
            "week_start": week_start.date().isoformat(),
            "shipments": shipments,
            "on_time_rate": pct(on_time),
            "tender_accept_rate": pct(accept),
            "claims": claims,
            "claims_ratio": pct(claims / shipments),
            "avg_cost_per_mile": cpm,
            "avg_transit_hours": transit,
            "capacity_utilization": pct(utilization),
        })
    return weeks


def summarize_performance(weeks, carrier):
    on_time = [w["on_time_rate"] for w in weeks]
    accept = [w["tender_accept_rate"] for w in weeks]
    claims_ratio = [w["claims_ratio"] for w in weeks]
    cpm = [w["avg_cost_per_mile"] for w in weeks]
    ship = [w["shipments"] for w in weeks]
    recent = weeks[-max(1, len(weeks) // 4):]  # last quarter of the window
    return {
        "weeks_observed": len(weeks),
        "on_time_rate_mean": pct(mean(on_time)),
        "on_time_rate_stdev": pct(stdev(on_time)),
        "on_time_trend_per_week": pct(slope(on_time), 5),
        "tender_accept_rate_mean": pct(mean(accept)),
        "claims_ratio_mean": pct(mean(claims_ratio)),
        "avg_cost_per_mile_mean": money(mean(cpm)),
        "recent_cost_per_mile": money(mean([w["avg_cost_per_mile"] for w in recent])),
        "avg_weekly_shipments": round(mean(ship), 1),
        "recent_weekly_shipments": round(mean([w["shipments"] for w in recent]), 1),
        "recent_capacity_utilization": pct(
            mean([w["capacity_utilization"] for w in recent])),
    }


# ----------------------------------------------------------------------------
# Step 3: diagnostics -> findings (what to act on before trusting the summary)
# ----------------------------------------------------------------------------

def diagnose(carrier, perf, args):
    findings = []
    cid, name = carrier["id"], carrier["name"]

    def add(kind, sev, evidence):
        findings.append({"carrier_id": cid, "carrier": name,
                         "type": kind, "severity": sev, "evidence": evidence})

    # SLA: on-time delivery
    if perf["on_time_rate_mean"] < args.ontime_target:
        gap = (args.ontime_target - perf["on_time_rate_mean"]) / args.ontime_target
        add("sla_ontime_breach", severity(gap),
            f"on-time {perf['on_time_rate_mean']:.3f} < target {args.ontime_target:.3f}")

    # SLA: tender acceptance
    if perf["tender_accept_rate_mean"] < args.accept_target:
        gap = (args.accept_target - perf["tender_accept_rate_mean"]) / args.accept_target
        add("sla_acceptance_breach", severity(gap),
            f"acceptance {perf['tender_accept_rate_mean']:.3f} < target {args.accept_target:.3f}")

    # Claims ratio
    if perf["claims_ratio_mean"] > args.claims_limit:
        over = (perf["claims_ratio_mean"] - args.claims_limit) / args.claims_limit
        add("high_claims", severity(over),
            f"claims ratio {perf['claims_ratio_mean']:.3f} > limit {args.claims_limit:.3f}")

    # Cost drift vs baseline
    base = carrier["baseline_cost_per_mile"]
    if base > 0:
        drift = (perf["recent_cost_per_mile"] - base) / base
        if drift > args.cost_drift:
            add("cost_drift", severity(drift),
                f"recent ${perf['recent_cost_per_mile']:.2f}/mi vs baseline "
                f"${base:.2f}/mi (+{drift * 100:.1f}%)")

    # Volume shortfall vs commitment
    commit = carrier["committed_weekly_volume"]
    if commit > 0:
        short = (commit - perf["recent_weekly_shipments"]) / commit
        if short > args.volume_shortfall:
            add("volume_shortfall", severity(short),
                f"recent {perf['recent_weekly_shipments']:.0f}/wk vs commit "
                f"{commit}/wk (-{short * 100:.1f}%)")

    # Capacity risk (over-reliance, no headroom left)
    if perf["recent_capacity_utilization"] > 0.92:
        add("capacity_risk", "moderate",
            f"recent utilization {perf['recent_capacity_utilization']:.3f} (little headroom)")

    # Declining performance trend
    if perf["on_time_trend_per_week"] < -0.003:
        add("declining_trend", "moderate",
            f"on-time slope {perf['on_time_trend_per_week']:+.5f}/wk")

    # Contract expiry window
    dte = carrier["days_to_expiry"]
    if 0 <= dte <= args.contract_warn:
        add("contract_expiring", "high" if dte <= 14 else "moderate",
            f"contract ends in {dte} days")
    elif dte < 0:
        add("contract_lapsed", "critical", f"contract lapsed {-dte} days ago")

    return findings


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    args = parse_args()
    rng = random.Random(args.seed)
    as_of = datetime.now()

    roster = build_roster(rng, args, as_of)

    carriers_out = []
    all_findings = []
    for carrier in roster:
        weeks = sample_weeks(rng, carrier, args, as_of)
        perf = summarize_performance(weeks, carrier)
        all_findings.extend(diagnose(carrier, perf, args))

        public = {k: v for k, v in carrier.items() if not k.startswith("_")}
        public["performance"] = perf
        public["weekly_samples"] = weeks
        carriers_out.append(public)

    by_severity = {"critical": 0, "high": 0, "moderate": 0}
    for f in all_findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    report = {
        "skill": "carrier-relationship-management",
        "skill_id": "SK033",
        "sub_agent": "SubAgent_33 (AG33)",
        "owner": "Tarun",
        "simulated": True,
        "generated_at": as_of.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "carriers": args.carriers,
            "lookback_weeks": args.lookback,
            "seed": args.seed,
            "ontime_target": args.ontime_target,
            "accept_target": args.accept_target,
            "claims_limit": args.claims_limit,
            "cost_drift": args.cost_drift,
            "volume_shortfall": args.volume_shortfall,
            "contract_warn_days": args.contract_warn,
        },
        "carrier_count": len(carriers_out),
        "carriers": carriers_out,
        "findings": all_findings,
        "findings_by_severity": by_severity,
    }

    write(report, args.out)


def write(report, path):
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
    fnd = report.get("findings", [])
    print(f"[SK033] wrote {path}")
    print(f"[SK033] carriers: {report['carrier_count']}  findings: {len(fnd)}")
    sev = report.get("findings_by_severity", {})
    print(f"[SK033] severity -> critical:{sev.get('critical', 0)} "
          f"high:{sev.get('high', 0)} moderate:{sev.get('moderate', 0)}")


if __name__ == "__main__":
    main()
