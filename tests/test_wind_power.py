import numpy as np
import pytest

from config import Config
from environment import EnergySystemEnv


@pytest.fixture
def env():
    environment = EnergySystemEnv.__new__(EnergySystemEnv)
    environment.physical_params = Config.PHYSICAL_PARAMS
    return environment


def test_wind_power_boundary_values(env):
    params = env.physical_params['wind_turbine']
    rated_power = params['rated_power']

    assert env._calculate_wind_power(0.0) == 0.0
    assert env._calculate_wind_power(params['cut_in_speed']) == 0.0
    assert env._calculate_wind_power(params['rated_speed']) == rated_power
    assert env._calculate_wind_power(params['cut_out_speed']) == rated_power
    assert env._calculate_wind_power(params['cut_out_speed'] + 0.01) == 0.0


def test_wind_power_is_strictly_increasing_between_cut_in_and_rated(env):
    params = env.physical_params['wind_turbine']
    speeds = np.linspace(
        params['cut_in_speed'], params['rated_speed'], num=1001
    )
    powers = np.array([env._calculate_wind_power(speed) for speed in speeds])

    assert np.all(np.diff(powers) > 0.0)


def test_wind_power_stays_within_rated_power(env):
    params = env.physical_params['wind_turbine']
    speeds = np.linspace(0.0, 30.0, num=3001)
    powers = np.array([env._calculate_wind_power(speed) for speed in speeds])

    assert np.all(powers >= 0.0)
    assert np.all(powers <= params['rated_power'])
