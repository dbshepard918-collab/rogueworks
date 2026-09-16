import os, sys, json
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, '.')

import pygame
from game.systems import save
from game.engine.scenes import Game
import argparse

args = argparse.Namespace(
    seed='0', daily=False, curses=None, endless=False,
    headless=True, turns=500, script=None, record=None,
    replay=None, shot=None, shot_dir=None,
    floor=1, new_run=True, log=None, save='save.json',
    frames=None, resolution=None, fullscreen=False, vsync=False,
    fps=None, data_dir=None, mod_dir=None
)

profile, notes = save.load_profile('save.json')
profile['run'] = None

game = Game(args, profile, notes, headless=True, save_path='save.json')
game.world.headless = True
game.start_run()

# Run some ticks
for i in range(200):
    game.world.tick(1/60)

# Render frame
surface = pygame.Surface((1280, 720))
game.world.renderer.draw(game.world, surface, 1/60)
pygame.image.save(surface, 'runs/shots/debug_frame.png')

# Analyze for text-like regions
import numpy as np
pixels = pygame.surfarray.array3d(surface)

text_regions = []
for ty in range(0, 22):
    for tx in range(0, 40):
        x0, y0 = tx * 32, ty * 32
        region = pixels[y0:y0+32, x0:x0+32]
        unique = len(np.unique(region.reshape(-1, 3), axis=0))
        if unique > 15:
            text_regions.append((tx, ty, unique))

print(f"High-detail regions (possible text): {len(text_regions)}")
for tx, ty, u in text_regions[:20]:
    x, y = tx * 32, ty * 32
    print(f"  pixel ({x},{y}) tile ({tx},{ty}): {u} unique colors")

# Also check player entity
player = game.world.player
print(f"\nPlayer:")
print(f"  sprite: {player.sprite}")
print(f"  position: ({player.x}, {player.y})")
print(f"  alive: {player.alive}")

# Check entities
print(f"\nEntities: {len(game.world.entities)}")
for e in game.world.entities[:10]:
    print(f"  {e.eid}: sprite={e.sprite}, pos=({e.x:.0f},{e.y:.0f})")

pygame.quit()
