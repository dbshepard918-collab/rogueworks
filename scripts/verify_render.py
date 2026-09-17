import pygame, os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
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
world = game.run_headless(turns=200)

surface = pygame.Surface((1280, 720))
world.renderer.draw(world, surface, 1/60)
pygame.image.save(surface, 'runs/shots/verify_64x64.png')

pixels = pygame.surfarray.array3d(surface)
unique = len(np.unique(pixels.reshape(-1, 3), axis=0))
print(f"Unique colors: {unique}")

player = world.player
monsters = [e for e in world.entities if e.eid != 'player']
print(f"Player: {player.sprite} at ({player.x:.0f},{player.y:.0f})")
print(f"Monsters: {len(monsters)}")

for m in monsters[:5]:
    frame_name = m.current_frame()[0] if hasattr(m, 'current_frame') else 'unknown'
    print(f"  {m.eid}: sprite={m.sprite}, frame={frame_name}")

pygame.quit()
