"""Deterministic RNG - the ONLY source of randomness in game/.

docs/CONTRACTS.md section 2: every random draw goes through RNG(seed) exposing
randint/random/choice/shuffle/weighted so that ``--seed N`` reproduces layout,
spawns, loot and level-ups exactly.

Implementation is xorshift64* seeded through SplitMix64.  Pure integer maths,
so it is bit-identical on every platform and Python build.  The stdlib
``random`` module is never imported anywhere inside ``game/``.
"""

MASK64 = 0xFFFFFFFFFFFFFFFF


def _splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return (z ^ (z >> 31)) & MASK64


def _hash_label(label):
    """FNV-1a over a utf-8 label -> 64 bit int."""
    h = 0xCBF29CE484222325
    for byte in str(label).encode("utf-8"):
        h ^= byte
        h = (h * 0x100000001B3) & MASK64
    return h


class RNG:
    """Seeded xorshift64* stream.  Never instantiate with wall-clock time."""

    __slots__ = ("state", "seed", "calls")

    def __init__(self, seed=0):
        self.seed = int(seed) & MASK64
        self.state = _splitmix64(self.seed)
        if self.state == 0:
            self.state = 0x9E3779B97F4A7C15
        self.calls = 0
        # discard a few outputs so low seeds do not correlate
        for _ in range(4):
            self._next()

    # -- core ------------------------------------------------------------
    def _next(self):
        x = self.state
        x ^= (x >> 12) & MASK64
        x = (x ^ (x << 25) & MASK64) ^ (x << 25) & MASK64
        x = (x ^ (x >> 27) & MASK64) ^ (x >> 27) & MASK64
        self.state = x & MASK64
        self.calls += 1
        return self.state

    def _next_float(self):
        return (self._next() >> 11) * (1.0 / 9007199254740992.0)

    def _next_upper(self, n):
        """0 <= result < n, unbiased for n much smaller than 2**64."""
        if n <= 0:
            return 0
        limit = (MASK64 // n) * n
        while True:
            r = self._next()
            if r < limit:
                return r % n

    # -- public API -------------------------------------------------------
    def randint(self, a, b):
        """Inclusive integer range [a, b]."""
        if a > b:
            a, b = b, a
        return a + self._next_upper(b - a + 1)

    def random(self):
        return self._next_float()

    def chance(self, p):
        """True with probability p (0..1)."""
        if p <= 0.0:
            return False
        if p >= 1.0:
            return True
        return self._next_float() < p

    def choice(self, seq):
        if not seq:
            raise ValueError("choice from empty sequence")
        return seq[self._next_upper(len(seq))]

    def shuffle(self, seq):
        n = len(seq)
        for i in range(n - 1, 0, -1):
            j = self._next_upper(i + 1)
            seq[i], seq[j] = seq[j], seq[i]

    def weighted(self, pairs, default=None):
        """Return a randomly chosen (value, weight) pair by weight.

        ``pairs`` is an iterable of ``(value, weight)`` where weight >= 0.
        Returns *default* when the total weight is zero.
        """
        total = 0.0
        seen = []
        for value, weight in pairs:
            try:
                w = float(weight)
            except (TypeError, ValueError):
                w = 0.0
            if w <= 0.0:
                continue
            total += w
            seen.append((value, w, total))
        if total <= 0.0:
            return default
        r = self._next_float() * total
        for value, w, cum in seen:
            if r < cum:
                return value
        return seen[-1][0]

    def weighted_index(self, weights):
        """Return an index into *weights* (list of non-negative floats)."""
        if not weights:
            return 0
        total = 0.0
        for w in weights:
            try:
                total += float(w)
            except (TypeError, ValueError):
                pass
        if total <= 0.0:
            return 0
        r = self._next_float() * total
        cum = 0.0
        for i, w in enumerate(weights):
            try:
                cum += float(w)
            except (TypeError, ValueError):
                continue
            if r < cum:
                return i
        return len(weights) - 1

    def fork(self, label):
        """Return a child RNG that stays deterministic from the parent seed."""
        child_seed = _hash_label("%d:%s" % (self.seed, label))
        child = object.__new__(RNG)
        child.seed = child_seed
        child.state = _splitmix64(child_seed)
        if child.state == 0:
            child.state = 0x9E3779B97F4A7C15
        child.calls = 0
        for _ in range(4):
            child._next()
        return child
