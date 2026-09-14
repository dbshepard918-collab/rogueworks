import sys
sys.path.insert(0, '/c/Users/dbshe/rogueworks')
from game.engine.audio import Audio, play, load_audio_cue, _BIOME_AMBIENCE
print("imports OK")
print("drowned_vaults:", _BIOME_AMBIENCE['drowned_vaults'])
a = Audio(enabled=False)
print("Audio(enabled=False) OK")
