from raspdash.providers.base import VehicleData, VehicleProvider
from raspdash.providers.elm327 import Elm327Provider
from raspdash.providers.hexv2 import HexV2Provider
from raspdash.providers.simulated import SimulatedProvider


PROVIDERS = {
    "simulated": SimulatedProvider,
    "hexv2": HexV2Provider,
    "elm327": Elm327Provider,
}


def create_provider(name: str, config: dict) -> VehicleProvider:
    provider_class = PROVIDERS.get(name, SimulatedProvider)
    return provider_class(config)


__all__ = [
    "Elm327Provider",
    "HexV2Provider",
    "SimulatedProvider",
    "VehicleData",
    "VehicleProvider",
    "create_provider",
]

