import numpy as np
import pytest

from config import Config
from environment import EnergySystemEnv


@pytest.fixture
def env():
    environment = EnergySystemEnv.__new__(EnergySystemEnv)
    environment.physical_params = Config.PHYSICAL_PARAMS
    environment.soc = Config.PHYSICAL_PARAMS['battery']['initial_soc']
    return environment


def assert_balanced(result):
    assert result['power_balance_residual'] == pytest.approx(0.0, abs=1e-9)
    assert (
        result['renewable_power'] + result['actual_discharge_power']
    ) == pytest.approx(
        result['actual_electrolyzer_power']
        + result['actual_charge_power']
        + result['curtailment_power']
    )


def test_no_renewable_power_records_requested_deficit(env):
    result = env._apply_physical_model(
        wind_power=0.0,
        pv_power=0.0,
        battery_power=0.0,
        electrolyzer_powers=[500.0] * 4,
    )

    assert result['requested_electrolyzer_power'] == pytest.approx(2000.0)
    assert result['actual_electrolyzer_power'] == pytest.approx(0.0)
    assert result['requested_power_deficit'] == pytest.approx(2000.0)
    assert result['curtailment_power'] == pytest.approx(0.0)
    assert_balanced(result)


def test_exact_power_balance_has_no_deficit_or_curtailment(env):
    result = env._apply_physical_model(
        wind_power=2000.0,
        pv_power=0.0,
        battery_power=0.0,
        electrolyzer_powers=[500.0] * 4,
    )

    assert result['requested_electrolyzer_power'] == pytest.approx(2000.0)
    assert result['actual_electrolyzer_power'] == pytest.approx(2000.0)
    assert result['requested_power_deficit'] == pytest.approx(0.0)
    assert result['curtailment_power'] == pytest.approx(0.0)
    assert_balanced(result)


def test_surplus_power_charges_battery_before_curtailment(env):
    result = env._apply_physical_model(
        wind_power=3000.0,
        pv_power=0.0,
        battery_power=1000.0,
        electrolyzer_powers=[500.0] * 4,
    )

    expected_soc = 0.5 + 0.95 * 1000.0 / 5963.2
    assert result['actual_charge_power'] == pytest.approx(1000.0)
    assert result['new_soc'] == pytest.approx(expected_soc)
    assert result['requested_power_deficit'] == pytest.approx(0.0)
    assert result['curtailment_power'] == pytest.approx(0.0)
    assert_balanced(result)


def test_full_battery_turns_unaccepted_charge_into_curtailment(env):
    env.soc = 1.0
    result = env._apply_physical_model(
        wind_power=3000.0,
        pv_power=0.0,
        battery_power=1000.0,
        electrolyzer_powers=[500.0] * 4,
    )

    assert result['actual_charge_power'] == pytest.approx(0.0)
    assert result['new_soc'] == pytest.approx(1.0)
    assert result['requested_power_deficit'] == pytest.approx(0.0)
    assert result['curtailment_power'] == pytest.approx(1000.0)
    assert_balanced(result)


def test_24_hour_energy_totals_match_hourly_histories():
    environment = EnergySystemEnv(mode='test')
    actions = [np.array([0.25])] + [np.array([0.2])] * 4
    hourly_results = []

    for _ in range(24):
        _, _, done, info = environment.step(actions)
        hourly_results.append(info)
        assert info['power_balance_residual'] == pytest.approx(0.0, abs=1e-9)

    assert done
    assert environment.total_renewable_energy == pytest.approx(
        sum(environment.renewable_power_history)
    )
    assert environment.total_charge_energy == pytest.approx(
        sum(environment.actual_charge_power_history)
    )
    assert environment.total_discharge_energy == pytest.approx(
        sum(environment.actual_discharge_power_history)
    )
    assert environment.total_electrolyzer_energy == pytest.approx(
        sum(environment.actual_electrolyzer_power_history)
    )
    assert environment.total_curtailment_energy == pytest.approx(
        sum(environment.curtailment_power_history)
    )
    assert environment.total_requested_power_deficit_energy == pytest.approx(
        sum(environment.requested_power_deficit_history)
    )
    assert environment.total_renewable_energy + environment.total_discharge_energy == pytest.approx(
        environment.total_electrolyzer_energy
        + environment.total_charge_energy
        + environment.total_curtailment_energy
    )

    final_info = hourly_results[-1]
    assert final_info['total_renewable_energy'] == pytest.approx(
        environment.total_renewable_energy
    )
    assert final_info['total_curtailment_energy'] == pytest.approx(
        environment.total_curtailment_energy
    )
