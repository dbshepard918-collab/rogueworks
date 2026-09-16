import os, sys, json, argparse
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, '.')

from game.systems import save
from game.engine.scenes import Game
import pygame

args = argparse.Namespace(
    seed='0', daily=False, curses=None, endless=False,
    headless=True, turns=500, script=None, record=None,
    replay=None, shot='100,200,300', shot_dir='runs/shots',
    floor=1, new_run=True, log=None, save='save.json',
    frames=None, resolution=None, fullscreen=False, vsync=False,
    fps=None, data_dir=None, mod_dir=None
)

profile, notes = save.load_profile('save.json')
profile['run'] = None

game = Game(args, profile, notes, headless=True, save_path='save.json')
game.start_run()

for i in range(300):
    game.world.tick(1/60)

os.makedirs('runs/shots', exist_ok=True)

# Render a frame
surface = pygame.Surface((1280, 720))
game.world.renderer.draw(game.world, surface, 1/60)

# Check for debug labels by looking at unique colors in the tile region
# The debug labels would be text rendered on tiles
pixels = pygame.surfarray.array3d(surface)
print(f"Rendered frame: {surface.get_size()}")

# Count unique colors (debug text would introduce many unique colors)
import numpy as np
unique_colors = len(np.unique(pixels.reshape(-1, 3), axis=0))
print(f"Unique colors in frame: {unique_colors}")

# Check specific regions for text
# The "TB" label would be in the top region where tiles are
top_region = pixels[:200, :, :]
unique_top = len(np.unique(top_region.reshape(-1, 3), axis=0))
print(f"Unique colors in top 200px: {unique_top}")

pygame.image.save(surface, 'runs/shots/debug_check.png')
print("Saved: runs/shots/debug_check.png")

pygame.quit()
