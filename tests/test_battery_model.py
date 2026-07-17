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


def test_battery_configuration_matches_selected_enerone_system():
    params = Config.PHYSICAL_PARAMS['battery']

    assert params['model'] == 'CATL EnerOne 1P (16 cabinets)'
    assert params['capacity'] == pytest.approx(16 * 372.7)
    assert params['max_charge_power'] == pytest.approx(5963.2)
    assert params['max_discharge_power'] == pytest.approx(5963.2)
    assert params['charge_efficiency'] == pytest.approx(0.95)
    assert params['discharge_efficiency'] == pytest.approx(0.95)
    assert params['initial_soc'] == pytest.approx(0.5)


@pytest.mark.parametrize(
    ('action', 'expected_power'),
    [(-1.0, -5963.2), (0.0, 0.0), (0.5, 2981.6), (1.0, 5963.2)],
)
def test_battery_action_scaling(env, action, expected_power):
    assert env._scale_battery_action(action) == pytest.approx(expected_power)


def test_battery_action_scaling_clips_and_rejects_invalid_values(env):
    assert env._scale_battery_action(2.0) == pytest.approx(5963.2)
    assert env._scale_battery_action(-2.0) == pytest.approx(-5963.2)

    with pytest.raises(ValueError, match='finite'):
        env._scale_battery_action(np.nan)


def test_one_hour_charge_matches_soc_equation(env):
    result = env._apply_physical_model(
        wind_power=1200.0,
        pv_power=0.0,
        battery_power=1000.0,
        electrolyzer_powers=[0.0] * 4,
    )
    expected_soc = 0.5 + 0.95 * 1000.0 / 5963.2

    assert result['actual_charge_power'] == pytest.approx(1000.0)
    assert result['actual_discharge_power'] == 0.0
    assert result['new_soc'] == pytest.approx(expected_soc)


def test_one_hour_discharge_matches_soc_equation(env):
    result = env._apply_physical_model(
        wind_power=0.0,
        pv_power=0.0,
        battery_power=-1000.0,
        electrolyzer_powers=[500.0] * 4,
    )
    expected_soc = 0.5 - 1000.0 / (0.95 * 5963.2)

    assert result['actual_charge_power'] == 0.0
    assert result['actual_discharge_power'] == pytest.approx(1000.0)
    assert result['new_soc'] == pytest.approx(expected_soc)


def test_soc_limits_prevent_charge_and_discharge(env):
    env.soc = 0.8
    charge_result = env._apply_physical_model(
        1200.0, 0.0, 1000.0, [0.0] * 4
    )
    assert charge_result['actual_charge_power'] == 0.0
    assert charge_result['new_soc'] == pytest.approx(0.8)

    env.soc = 0.2
    discharge_result = env._apply_physical_model(
        0.0, 0.0, -1000.0, [500.0] * 4
    )
    assert discharge_result['actual_discharge_power'] == 0.0
    assert discharge_result['new_soc'] == pytest.approx(0.2)


def test_soc_headroom_limits_power_before_soc_update(env):
    env.soc = 0.79
    result = env._apply_physical_model(
        wind_power=7000.0,
        pv_power=0.0,
        battery_power=5963.2,
        electrolyzer_powers=[0.0] * 4,
    )
    expected_limit = (0.8 - 0.79) * 5963.2 / 0.95

    assert result['actual_charge_power'] == pytest.approx(expected_limit)
    assert result['new_soc'] == pytest.approx(0.8)


def test_supply_direction_rejects_conflicting_battery_requests(env):
    charge_during_deficit = env._apply_physical_model(
        0.0, 0.0, 1000.0, [500.0] * 4
    )
    assert charge_during_deficit['actual_charge_power'] == 0.0
    assert charge_during_deficit['adjusted_battery_power'] == 0.0

    discharge_during_surplus = env._apply_physical_model(
        3000.0, 0.0, -1000.0, [500.0] * 4
    )
    assert discharge_during_surplus['actual_discharge_power'] == 0.0
    assert discharge_during_surplus['adjusted_battery_power'] == 0.0


def test_zero_action_is_not_overwritten_by_power_balance(env):
    result = env._apply_physical_model(
        3000.0, 0.0, 0.0, [500.0] * 4
    )

    assert result['requested_battery_power'] == 0.0
    assert result['actual_charge_power'] == 0.0
    assert result['actual_discharge_power'] == 0.0
    assert result['adjusted_battery_power'] == 0.0
    assert result['new_soc'] == pytest.approx(0.5)


def test_step_exposes_requested_and_actual_battery_power():
    environment = EnergySystemEnv(mode='test')
    actions = [np.array([0.25])] + [np.array([0.0])] * 4

    _, _, _, info = environment.step(actions)

    assert info['requested_battery_power'] == pytest.approx(1490.8)
    assert info['actual_battery_power'] == info['battery_power']
    assert info['actual_battery_power'] == pytest.approx(
        info['actual_charge_power'] - info['actual_discharge_power']
    )
    assert environment.requested_battery_power_history[-1] == pytest.approx(
        info['requested_battery_power']
    )
    assert environment.battery_power_history[-1] == pytest.approx(
        info['actual_battery_power']
    )
