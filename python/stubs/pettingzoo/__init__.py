"""Minimal PettingZoo stub for the GitHub Pages / Pyodide build.

Mirrors the helper methods AFWIPEnv calls on AECEnv (_clear_rewards, etc.).
"""


class AECEnv:
    """Enough of the AEC API for AFWIPEnv to construct and run in-browser."""

    metadata = {}
    possible_agents = []
    agents = []
    agent_selection = None
    terminations = {}
    truncations = {}
    rewards = {}
    _cumulative_rewards = {}
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

    @property
    def num_agents(self):
        return len(self.agents)

    @property
    def max_num_agents(self):
        return len(self.possible_agents)

    def _clear_rewards(self):
        for agent in self.rewards:
            self.rewards[agent] = 0

    def _accumulate_rewards(self):
        for agent, reward in self.rewards.items():
            self._cumulative_rewards[agent] = (
                self._cumulative_rewards.get(agent, 0) + reward
            )

    def _deads_step_first(self):
        deads = [
            agent
            for agent in self.agents
            if (self.terminations.get(agent) or self.truncations.get(agent))
        ]
        if deads:
            self._skip_agent_selection = self.agent_selection
            self.agent_selection = deads[0]
        return self.agent_selection

    def _was_dead_step(self, action):
        if action is not None:
            raise ValueError("when an agent is dead, the only valid action is None")
        agent = self.agent_selection
        del self.terminations[agent]
        del self.truncations[agent]
        del self.rewards[agent]
        del self._cumulative_rewards[agent]
        del self.infos[agent]
        self.agents.remove(agent)
        deads = [
            a
            for a in self.agents
            if (self.terminations.get(a) or self.truncations.get(a))
        ]
        if deads:
            if getattr(self, "_skip_agent_selection", None) is None:
                self._skip_agent_selection = self.agent_selection
            self.agent_selection = deads[0]
        else:
            if getattr(self, "_skip_agent_selection", None) is not None:
                self.agent_selection = self._skip_agent_selection
            self._skip_agent_selection = None
        self._clear_rewards()

    def last(self, observe=True):
        agent = self.agent_selection
        observation = self.observe(agent) if observe else None
        return (
            observation,
            self._cumulative_rewards[agent],
            self.terminations[agent],
            self.truncations[agent],
            self.infos[agent],
        )
