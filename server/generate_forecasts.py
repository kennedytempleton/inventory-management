"""
Script to generate demand forecasts keyed to real inventory SKUs.

The original demand_forecasts.json referenced a legacy product catalog (WDG-001,
BRG-102, ...) that no longer exists in inventory.json, so only 1 of its 9 records
could be joined to an inventory item. That broke any feature needing both demand
and cost data, and made Demand.vue collapse to a single row whenever a filter was
applied. This regenerates forecasts against SKUs that actually exist.

Run from the server/ directory:  python3 generate_forecasts.py
"""
import json
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Fixed seed so regenerating produces identical output — the JSON file is
# committed, and a churning diff on every run would be noise.
random.seed(20260824)

# SKUs to forecast, grouped by the trend we want them to show. The mix is
# deliberate: enough "increasing" items to give the restocking recommender real
# signal to rank on, and a spread across all three warehouses and all five
# categories so the Location/Category filters have something to narrow.
#
# The four SKUs currently below their reorder point (TMP-201, SRV-301, SRV-302,
# PSU-508) are all included and skewed toward rising demand, so the most urgent
# restock candidates are also the most expensive ones — that is what makes a
# budget constraint interesting rather than trivially satisfiable.
INCREASING = [
    'TMP-201',  # short: 125 on hand vs 150 reorder point
    'SRV-301',  # short: 45 vs 50, and $445/unit
    'PSU-508',  # short: 75 vs 100, and $185.50/unit
    'ACC-206',
    'HMD-202',
    'PSU-505',
    'PSU-507',
    'STP-303',
    'LED-406',
    'PCB-003',
]

STABLE = [
    'SRV-302',  # short: 28 vs 30, the single most expensive item at $725/unit
    'PSU-501',
    'PSU-502',
    'PCB-001',
    'GYR-207',
    'LDR-208',
    'PLY-901',
    'DRV-405',
    'STP-304',
]

DECREASING = [
    'PRX-204',
    'MCU-401',
    'PWM-404',
    'SPR-602',
    'PRS-203',
]

# Multiplier ranges per trend. The stable band is intentionally within +/-2%
# because Demand.vue's getChangeColor() treats anything inside 2% as flat — a
# record labelled "stable" that moved 8% would render with a contradictory colour.
TREND_RANGES = {
    'increasing': (1.15, 1.60),
    'stable': (0.985, 1.015),
    'decreasing': (0.60, 0.85),
}


def build_forecasts():
    with open(os.path.join(DATA_DIR, 'inventory.json')) as f:
        inventory = {item['sku']: item for item in json.load(f)}

    plan = (
        [(sku, 'increasing') for sku in INCREASING]
        + [(sku, 'stable') for sku in STABLE]
        + [(sku, 'decreasing') for sku in DECREASING]
    )

    missing = [sku for sku, _ in plan if sku not in inventory]
    if missing:
        raise SystemExit(f"SKUs not present in inventory.json: {', '.join(missing)}")

    forecasts = []
    for index, (sku, trend) in enumerate(plan, start=1):
        item = inventory[sku]

        # Anchor demand to the reorder point rather than to stock on hand, so an
        # overstocked item doesn't get an implausibly large forecast attached to it.
        current_demand = int(item['reorder_point'] * random.uniform(0.8, 1.6))
        low, high = TREND_RANGES[trend]
        forecasted_demand = int(current_demand * random.uniform(low, high))

        # A stable item whose rounding collapsed the delta to zero is fine, but a
        # non-stable one that rounds to no change would contradict its own label.
        if trend == 'increasing' and forecasted_demand <= current_demand:
            forecasted_demand = current_demand + 1
        if trend == 'decreasing' and forecasted_demand >= current_demand:
            forecasted_demand = max(1, current_demand - 1)

        forecasts.append({
            'id': str(index),
            'item_sku': sku,
            'item_name': item['name'],
            'current_demand': current_demand,
            'forecasted_demand': forecasted_demand,
            'trend': trend,
            'period': 'Next 30 days',
        })

    return forecasts, inventory


def main():
    forecasts, inventory = build_forecasts()

    out_path = os.path.join(DATA_DIR, 'demand_forecasts.json')
    with open(out_path, 'w') as f:
        json.dump(forecasts, f, indent=2)
        f.write('\n')

    print(f"Generated {len(forecasts)} forecasts -> {out_path}")

    by_trend = {}
    for forecast in forecasts:
        by_trend.setdefault(forecast['trend'], []).append(forecast)
    for trend in ('increasing', 'stable', 'decreasing'):
        print(f"  {trend:11} {len(by_trend.get(trend, []))}")

    warehouses = {inventory[f['item_sku']]['warehouse'] for f in forecasts}
    categories = {inventory[f['item_sku']]['category'] for f in forecasts}
    print(f"  warehouses covered: {', '.join(sorted(warehouses))}")
    print(f"  categories covered: {', '.join(sorted(categories))}")


if __name__ == '__main__':
    main()
