"""Tiny stand-ins for gymnasium.spaces used at AFWIPEnv construction time."""


class Space:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class Discrete(Space):
    def __init__(self, n, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = int(n)


class Box(Space):
    def __init__(self, low, high, shape=None, dtype=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.low = low
        self.high = high
        self.shape = shape
        self.dtype = dtype


class Dict(Space):
    def __init__(self, spaces=None, **kwargs):
        if spaces is None:
            spaces = kwargs
        super().__init__()
        self.spaces = spaces
