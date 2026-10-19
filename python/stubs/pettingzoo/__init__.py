"""Minimal PettingZoo stub for the GitHub Pages / Pyodide build."""


class AECEnv:
    """Enough of the AEC API for AFWIPEnv to construct and run in-browser."""

    metadata = {}
    possible_agents = []
    agents = []
    agent_selection = None
    terminations = {}
    truncations = {}
    rewards = {}
    infos = {}

    def __init__(self):
        pass

    def reset(self, seed=None, options=None):
        raise NotImplementedError

    def step(self, action):
        raise NotImplementedError

    def observe(self, agent):
        raise NotImplementedError

    def close(self):
        pass
