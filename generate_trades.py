import json
from datetime import datetime, timedelta

# Calculate expiry dates
today = datetime(2026, 5, 26)
expiry_3m = (today + timedelta(days=90)).strftime('%Y-%m')
expiry_6m = (today + timedelta(days=180)).strftime('%Y-%m')

recommendations = [
    {
        'rank': 1,
        'underlying': 'COIL',
        'structure': 'naked_call',
        'legs': [
            {'strike': 120, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'BUY', 'price': 0.36}
        ],
        'entry_cost': 0.36,
        'max_loss': 0.36,
        'max_profit': 95.0,
        'expected_value': 20.84,
        'payoff_ratio': 263.9,
        'ev_risk_ratio': 57.9,
        'target_scenario': 'Moderate Escalation + Major Disruption',
        'probability_edge': '+29.6% combined',
        'reasoning': 'Highest EV/risk ratio. Cheap lottery ticket on combined 63% AI probability of Brent ≥$115. Maximum position sizing: 5-10 contracts per $10k portfolio. Pure convexity play on geopolitical tail risk with massive asymmetry.'
    },
    {
        'rank': 2,
        'underlying': 'COIL',
        'structure': 'bull_call_spread',
        'legs': [
            {'strike': 110, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'BUY', 'price': 0.77},
            {'strike': 130, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'SELL', 'price': 0.20}
        ],
        'entry_cost': 0.57,
        'max_loss': 0.57,
        'max_profit': 19.43,
        'expected_value': 9.18,
        'payoff_ratio': 34.1,
        'ev_risk_ratio': 16.1,
        'target_scenario': 'Moderate Escalation',
        'probability_edge': '+18.3%',
        'reasoning': 'Best risk-defined spread. Captures Moderate Escalation ($100-$130) where AI sees 35% vs market 16.7%. Defined max loss with 34:1 payoff. Ideal core position for 2-3% portfolio allocation.'
    },
    {
        'rank': 3,
        'underlying': 'COIL',
        'structure': 'bull_call_spread',
        'legs': [
            {'strike': 100, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'BUY', 'price': 1.97},
            {'strike': 150, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'SELL', 'price': 0.10}
        ],
        'entry_cost': 1.87,
        'max_loss': 1.87,
        'max_profit': 48.13,
        'expected_value': 23.38,
        'payoff_ratio': 25.7,
        'ev_risk_ratio': 12.5,
        'target_scenario': 'Major Disruption',
        'probability_edge': '+11.3%',
        'reasoning': 'Wide spread captures both Moderate and Major scenarios (combined 63% AI prob). Higher premium but massive range $100-$150. Strong absolute EV ($23.38). Suitable for larger accounts seeking defined-risk exposure to escalation scenarios.'
    },
    {
        'rank': 4,
        'underlying': 'COIL',
        'structure': 'bull_call_spread',
        'legs': [
            {'strike': 120, 'expiry': expiry_6m, 'type': 'CALL', 'side': 'BUY', 'price': 1.48},
            {'strike': 150, 'expiry': expiry_6m, 'type': 'CALL', 'side': 'SELL', 'price': 0.43}
        ],
        'entry_cost': 1.05,
        'max_loss': 1.05,
        'max_profit': 28.95,
        'expected_value': 10.95,
        'payoff_ratio': 27.6,
        'ev_risk_ratio': 10.4,
        'target_scenario': 'Major Disruption',
        'probability_edge': '+11.3%',
        'reasoning': '6-month tenor provides more time for geopolitical developments. Targets Major Disruption scenario ($130-$180). Lower leverage than 3-month but better theta decay profile. Good diversification vs shorter-dated positions.'
    },
    {
        'rank': 5,
        'underlying': 'COIL',
        'structure': 'bull_call_spread',
        'legs': [
            {'strike': 100, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'BUY', 'price': 1.97},
            {'strike': 120, 'expiry': expiry_3m, 'type': 'CALL', 'side': 'SELL', 'price': 0.36}
        ],
        'entry_cost': 1.61,
        'max_loss': 1.61,
        'max_profit': 18.39,
        'expected_value': 11.64,
        'payoff_ratio': 11.4,
        'ev_risk_ratio': 7.2,
        'target_scenario': 'Moderate Escalation',
        'probability_edge': '+18.3%',
        'reasoning': 'Conservative ITM spread with delta ~0.26. Lower leverage but higher probability of profit. Breakeven at $101.61. Good for risk-averse accounts wanting exposure to most likely upside scenario (35% prob Moderate Escalation).'
    }
]

# Save to file
with open('trade_recommendations_2026-05-26.json', 'w') as f:
    json.dump(recommendations, f, indent=2)

print('TOP 5 TRADE RECOMMENDATIONS')
print('=' * 80)
for rec in recommendations:
    leg_str = f"{rec['legs'][0]['strike']}"
    if len(rec['legs']) > 1:
        leg_str += f"/{rec['legs'][1]['strike']}"
    
    print(f"\nRank {rec['rank']}: {rec['structure'].upper().replace('_', ' ')} - {leg_str}")
    print(f"  Target: {rec['target_scenario']} ({rec['probability_edge']})")
    print(f"  Entry: ${rec['entry_cost']:.2f} | Max Profit: ${rec['max_profit']:.2f} | EV: ${rec['expected_value']:.2f}")
    print(f"  Payoff Ratio: {rec['payoff_ratio']:.1f}:1 | EV/Risk: {rec['ev_risk_ratio']:.1f}x")
    print(f"  {rec['reasoning'][:120]}...")

print(f"\n\nSaved to: trade_recommendations_2026-05-26.json")
