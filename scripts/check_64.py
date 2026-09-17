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
game.world.headless = True
game.start_run()

for i in range(200):
    game.world.tick(1/60)

surface = pygame.Surface((1280, 720))
game.world.renderer.draw(game.world, surface, 1/60)
pygame.image.save(surface, 'runs/shots/64x64_check.png')

pixels = pygame.surfarray.array3d(surface)
unique_colors = len(np.unique(pixels.reshape(-1, 3), axis=0))
print(f'Unique colors: {unique_colors}')

player = game.world.player
print(f'Player: sprite={player.sprite}, pos=({player.x:.0f},{player.y:.0f})')

monsters = [e for e in game.world.entities if e.eid != 'player']
print(f'Monsters: {len(monsters)}')

pygame.quit()
print('Done')
