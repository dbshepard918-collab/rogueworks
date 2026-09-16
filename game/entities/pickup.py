"""Pickups: gold, essence, health orbs, keys, chests and dropped items."""

from .actor import Entity

TILE = 64

PICKUP_SPRITES = {
    "gold": "prop_gold_pile",
    "essence": "prop_essence",
    "health": "prop_potion_health",
    "key": "prop_key",
    "chest": "prop_chest",
    "item": "prop_backpack",
    "shop": "prop_table",
    "shrine": "prop_shrine",
}


class Pickup(Entity):
    kind = "pickup"

    def __init__(self, eid, x, y, pickup_kind, amount=0, item=None, sprite=None, magnet=True):
        super().__init__(eid, x, y, radius=20.0, sprite=sprite or PICKUP_SPRITES.get(pickup_kind, "pickup_item"))
        self.pickup_kind = pickup_kind
        self.amount = float(amount)
        self.item = item
        self.magnet = bool(magnet) and pickup_kind in ("gold", "essence", "health")
        self.collected = False
        self.bob = 0.0

    def tick(self, dt):
        self.tick_age(dt)
        self.bob += dt

    def label(self):
        if self.pickup_kind == "gold":
            return "%d gold" % int(self.amount)
        if self.pickup_kind == "essence":
            return "%d essence" % int(self.amount)
        if self.pickup_kind == "health":
            return "healing orb"
        if self.pickup_kind == "key":
            return "vault key"
        if self.pickup_kind == "chest":
            return "chest"
        if self.item is not None:
            return self.item.get("name", "item")
        return self.pickup_kind
