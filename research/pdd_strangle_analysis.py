"""Quick PDD strangle scenario comparison"""

stock = 101.97

combos = [
    ('3/20  95p/105c', 95, 105, 4.73),
    ('3/20  95p/110c', 95, 110, 3.10),
    ('3/27  95p/105c', 95, 105, 6.37),
    ('3/27  95p/110c', 95, 110, 4.71),
    ('4/17  95p/105c', 95, 105, 8.60),
    ('4/17  95p/110c', 95, 110, 6.70),
]

scenarios = [
    ('-20%', stock * 0.80),
    ('-14.5% (hist avg)', stock * 0.855),
    ('-10%', stock * 0.90),
    ('-5%', stock * 0.95),
    ('Flat', stock),
    ('+5%', stock * 1.05),
    ('+10%', stock * 1.10),
    ('+14.5% (hist avg)', stock * 1.145),
    ('+20%', stock * 1.20),
]

print('PDD Strangle Scenario Payoffs (intrinsic only — longer expiries retain extra time value)')
print()

# Header
header = '{:<22} {:>7}'.format('Scenario', 'Stock')
for label, _, _, cost in combos:
    header += ' | {:>15}'.format(label)
print(header)
print('-' * len(header))

for scenario_name, price in scenarios:
    line = '{:<22} {:>7.2f}'.format(scenario_name, price)
    for label, put_k, call_k, cost in combos:
        put_val = max(0, put_k - price)
        call_val = max(0, price - call_k)
        total_val = put_val + call_val
        pnl = total_val - cost
        pnl_pct = (pnl / cost) * 100
        line += ' | {:>+7.2f} ({:>+4.0f}%)'.format(pnl, pnl_pct)
    print(line)

print()
print('Cost per contract:')
for label, _, _, cost in combos:
    print('  {}: ${:.2f} (${:.0f})'.format(label, cost, cost * 100))

print()
print('Key insight: 3/20 has max gamma (biggest % gain on big moves) but dies if move')
print('takes days to develop. 3/27 and 4/17 cost more but capture the multi-day drift.')
