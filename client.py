from openenv.core.client import EnvClient
from models import SupportAction, SupportObservation, ActionType, ResolutionType


class SupportEnv(EnvClient):
    action_type = SupportAction
    observation_type = SupportObservation


def make_action(action_type: ActionType, **parameters) -> SupportAction:
    """Convenience function for building actions in the baseline agent."""
    return SupportAction(action_type=action_type, parameters=dict(parameters))
