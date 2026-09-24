from incidentlab.scenarios import scenarios

def test_scenario_catalog(): assert {x['id'] for x in scenarios()} == {f'C{i:02d}' for i in range(1,13)}
