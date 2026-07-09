import json
import sqlite3
from datetime import datetime

# Load assessment
with open('scenario_assessment_2026-06-10.json', 'r') as f:
    assessment = json.load(f)

# Save to database
conn = sqlite3.connect('db\\oil_data.db')
cursor = conn.cursor()

date = '2026-06-10'
created_at = datetime.now().isoformat()

price_ranges = {
    'Super Spike': (180, 250),
    'Major Disruption': (130, 180),
    'Moderate Escalation': (100, 130),
    'Current State': (80, 100),
    'De-escalation': (65, 80),
    'Resolution': (55, 65)
}

for scenario_name, data in assessment['scenarios'].items():
    brent_low, brent_high = price_ranges[scenario_name]
    
    cursor.execute('''
        INSERT INTO scenario_probabilities 
        (date, scenario_name, probability, brent_low, brent_high, reasoning, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date, scenario_name, data['probability'], brent_low, brent_high, 
          data['reasoning'], created_at))

conn.commit()
print(f'Saved {len(assessment["scenarios"])} scenarios to database\n')
conn.close()

# Display results
print('=' * 80)
print('SCENARIO PROBABILITY ASSESSMENT - June 10, 2026')
print('=' * 80)

for scenario, data in assessment['scenarios'].items():
    prob = data['probability']
    print(f'\n{scenario}: {prob*100:.1f}%')
    reasoning = data['reasoning']
    if len(reasoning) > 200:
        reasoning = reasoning[:200] + '...'
    print(f'  {reasoning}')

total = sum([d['probability'] for d in assessment['scenarios'].values()])
print(f'\n{"=" * 80}')
print(f'Total Probability: {total:.2f}')
print(f'\nOVERALL ASSESSMENT:')
print(f'{assessment["overall_assessment"]}')
print(f'\nKEY DRIVERS:')
for i, driver in enumerate(assessment['key_drivers'], 1):
    print(f'{i}. {driver}')
