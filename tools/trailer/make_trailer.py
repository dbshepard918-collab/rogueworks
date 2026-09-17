"""make_trailer.py — Depths of Vaelmoor cinematic trailer compositor."""
from __future__ import annotations
import math, os, random, subprocess, sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
except ImportError:
    sys.exit("Pillow + numpy required")

ROOT       = Path(__file__).resolve().parents[2]
SHOTS_ROOT = ROOT / "runs" / "trailer" / "shots"
FRAMES_OUT = ROOT / "runs" / "trailer" / "frames"
TRAILER_OUT= ROOT / "runs" / "trailer" / "depths_of_vaelmoor_trailer.mp4"
FONTS_DIR  = ROOT / "assets" / "fonts"

W, H, FPS = 1280, 720, 30

VOID=(11,10,16); STONE=(58,52,80); MID=(87,80,112); LIGHT=(138,132,150)
PALE=(217,210,197); GOLD=(232,178,60); CRIMSON=(196,99,95); GREEN=(121,176,74); TEAL=(100,180,200)

def _font(sz):
    cands=[]
    if FONTS_DIR.exists(): cands+=sorted(FONTS_DIR.glob("*.ttf"))
    wf=Path("C:/Windows/Fonts")
    if wf.exists(): cands+=[wf/n for n in ["consola.ttf","cour.ttf","lucon.ttf","arial.ttf"]]
    for p in cands:
        if p.exists():
            try: return ImageFont.truetype(str(p), sz)
            except: pass
    return ImageFont.load_default()

FT=_font(72); FS=_font(36); FB=_font(24); FL=_font(18)

def nb(): return Image.new("RGB",(W,H),VOID)
def tc(d,txt,y,font,col=PALE):
    bb=d.textbbox((0,0),txt,font=font); tw=bb[2]-bb[0]; x=(W-tw)//2
    d.text((x+2,y+2),txt,font=font,fill=(0,0,0)); d.text((x,y),txt,font=font,fill=col)
def tl(d,txt,x,y,font,col=PALE): d.text((x,y),txt,font=font,fill=col)

def vignette(img):
    arr=np.array(img,dtype=np.float32)
    cx,cy=W/2,H/2
    ys,xs=np.mgrid[0:H,0:W]
    dist=np.sqrt(((xs-cx)/(W*0.6))**2+((ys-cy)/(H*0.6))**2)
    factor=np.clip(1-0.55*dist**1.4,0,1)[...,np.newaxis]
    return Image.fromarray(np.clip(arr*factor,0,255).astype(np.uint8))

def letterbox(img,bars=56):
    out=img.copy(); d=ImageDraw.Draw(out)
    d.rectangle([0,0,W,bars],fill=(0,0,0)); d.rectangle([0,H-bars,W,H],fill=(0,0,0)); return out

def blend(a,b,t): return Image.blend(a,b,max(0.0,min(1.0,t)))
def hold(f,n): return [f.copy() for _ in range(n)]
def fade_in(f,n): blk=Image.new("RGB",(W,H),(0,0,0)); return [blend(blk,f,i/n) for i in range(n)]
def fade_out(f,n): blk=Image.new("RGB",(W,H),(0,0,0)); return [blend(f,blk,i/n) for i in range(n)]
def xfade(a,b,n): return [blend(a,b,i/n) for i in range(n)]
def wipe(a,b,n):
    out=[]
    for i in range(n):
        x=int(W*i/n); fr=a.copy(); fr.paste(b.crop((0,0,x,H)),(0,0)); out.append(fr)
    return out

def load_shot(p):
    img=Image.open(p).convert("RGB").resize((W,H)); return vignette(img)

def load_shots():
    shots=[]
    for sub in sorted(SHOTS_ROOT.iterdir()):
        if sub.is_dir():
            for png in sorted(sub.glob("*.png")): shots.append(load_shot(png))
    return shots

def title_card():
    img=nb(); d=ImageDraw.Draw(img)
    rng=random.Random(7)
    for _ in range(220):
        bx=rng.randint(0,W); by=rng.randint(0,H); v=rng.randint(14,24)
        d.rectangle([bx,by,bx+rng.randint(4,16),by+rng.randint(2,8)],fill=(v,v-2,v+2))
    for r in range(180,0,-3):
        a=max(0,int(28*(1-r/180)**1.4))
        d.ellipse([W//2-r,H//2-r*2//3,W//2+r,H//2+r*2//3],fill=(*GOLD,))
    # Re-darken
    overlay=Image.new("RGB",(W,H),VOID); img=Image.blend(img,overlay,0.62)
    d=ImageDraw.Draw(img)
    d.line([(120,H//2-68),(W-120,H//2-68)],fill=STONE,width=1)
    d.line([(120,H//2+82),(W-120,H//2+82)],fill=STONE,width=1)
    tc(d,"DEPTHS OF VAELMOOR",H//2-50,FT,GOLD)
    tc(d,"A ROGUELITE DESCENT",H//2+34,FS,PALE)
    tc(d,"ROGUEWORKS  \u2022  2026",H-52,FL,LIGHT)
    return img

def tagline_card(line1,line2="",col=PALE):
    img=nb(); d=ImageDraw.Draw(img)
    y=H//2-44 if line2 else H//2-20
    tc(d,line1,y,FS,col)
    if line2: tc(d,line2,y+56,FB,LIGHT)
    return img

def gameplay_card(shot,headline,sub="",col=GOLD):
    img=letterbox(shot,56); d=ImageDraw.Draw(img)
    bar_y=H-56
    for i in range(56): d.line([(0,bar_y+i),(W,bar_y+i)],fill=(0,0,0))
    tl(d,headline,36,bar_y+8,FB,col)
    if sub: tl(d,sub,36,bar_y+32,FL,LIGHT)
    return img

def end_card():
    img=nb(); d=ImageDraw.Draw(img)
    tc(d,"DEPTHS OF VAELMOOR",H//2-60,FS,GOLD)
    tc(d,"AVAILABLE NOW",H//2+6,FB,PALE)
    tc(d,"EVERY RUN ENDS.  KEEP DESCENDING.",H//2+52,FL,LIGHT)
    d.line([(200,H//2-14),(W-200,H//2-14)],fill=STONE,width=1)
    return img

def build(shots):
    F=FPS; seq=[]

    title=title_card()
    seq+=[Image.new("RGB",(W,H),(0,0,0))]*(F//2)
    seq+=fade_in(title,F//2)
    seq+=hold(title,F*3)

    t1=tagline_card("EVERY DUNGEON IS DIFFERENT.","Procedurally generated. No two runs the same.",PALE)
    seq+=xfade(title,t1,F//2); seq+=hold(t1,F*2)

    def gp(idx,h,s="",c=GOLD):
        return gameplay_card(shots[idx],h,s,c) if idx<len(shots) else None

    cards=[
        gp(0,"EXPLORE THE CATACOMBS","Navigate rooms, traps, and secrets",GOLD),
        gp(1,"DISCOVER HIDDEN PASSAGES","Crack walls — if you can find them",TEAL),
        gp(2,"FACE 100+ UNIQUE MONSTERS","Bone rats, flesh horrors, worse things",CRIMSON),
        gp(3,"MASTER YOUR BUILD","Items, abilities, and meta-upgrades persist",GREEN),
        gp(4,"DIE. RETURN. DESCEND AGAIN.","Death is a setback. Not the end.",PALE),
        gp(5,"KEEPER'S HALL — YOUR BASE","NPCs, upgrades, and the stair that calls",TEAL),
        gp(6,"DEEPER FLOORS AWAIT","5 biomes. Infinite threat.",GOLD),
        gp(7,"HOW FAR WILL YOU GO?","",CRIMSON),
        gp(8,"THE DARK IS WAITING.","",GOLD),
        gp(9,"EVERY RUN IS A STORY.","",PALE),
        gp(10,"FIGHT. FALL. RISE.","",GREEN),
        gp(11,"ONE MORE RUN.","",PALE),
    ]
    cards=[c for c in cards if c is not None]

    t2=tagline_card("DEATH IS NOT THE END.","Return. Rearm. Go deeper.",CRIMSON)
    last=seq[-1]
    seq+=xfade(last,t2,F//2); seq+=hold(t2,F*2)

    # Burst 1
    for i,card in enumerate(cards[:4]):
        last=seq[-1]
        seq+=wipe(last,card,F//3); seq+=hold(card,F+F//2)

    t3=tagline_card("5 BIOMES.  INFINITE PERIL.","Catacombs \u00b7 Ember Warrens \u00b7 Drowned Vaults \u00b7 and beyond",TEAL)
    last=seq[-1]
    seq+=xfade(last,t3,F//2); seq+=hold(t3,F*2)

    # Burst 2 — rapid cuts
    for i,card in enumerate(cards[4:9]):
        last=seq[-1]
        t=F//4 if i>0 else F//3
        seq+=wipe(last,card,t); seq+=hold(card,F)

    t4=tagline_card("PERMANENT META-PROGRESS.","Unlock upgrades between runs. Grow stronger.",GREEN)
    last=seq[-1]
    seq+=xfade(last,t4,F//2); seq+=hold(t4,F*2)

    # Burst 3 — final
    for card in cards[9:]:
        last=seq[-1]; seq+=wipe(last,card,F//3); seq+=hold(card,F+F//2)

    # End
    end=end_card()
    last=seq[-1]
    seq+=xfade(last,end,F//2); seq+=hold(end,F*3); seq+=fade_out(end,F)
    return seq

def write_frames(frames,out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    for old in out_dir.glob("trailer_*.png"): old.unlink()
    print(f"Writing {len(frames)} frames …")
    for i,f in enumerate(frames):
        f.save(out_dir/f"trailer_{i:05d}.png")
        if i%60==0: print(f"  {i}/{len(frames)}")
    print("Frames done.")

def encode(frames_dir,out):
    cmd=["ffmpeg","-y","-framerate",str(FPS),
         "-i",str(frames_dir/"trailer_%05d.png"),
         "-c:v","libx264","-preset","slow","-crf","16",
         "-pix_fmt","yuv420p","-vf","scale=1280:720:flags=lanczos",
         "-movflags","+faststart",str(out)]
    print(f"\nEncoding …"); r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode: print(r.stderr[-2000:]); sys.exit(f"ffmpeg failed {r.returncode}")
    mb=out.stat().st_size/1024/1024; dur=len(list(frames_dir.glob("trailer_*.png")))/FPS
    print(f"OK  {out.name}  {dur:.1f}s  {mb:.1f} MB")

def main():
    print("="*60); print("  Depths of Vaelmoor — Trailer Compositor"); print("="*60)
    shots=load_shots(); print(f"  {len(shots)} shots loaded")
    if not shots: sys.exit("No shots found in runs/trailer/shots/")
    frames=build(shots); print(f"  {len(frames)} frames ({len(frames)/FPS:.1f}s @ {FPS}fps)")
    write_frames(frames,FRAMES_OUT); encode(FRAMES_OUT,TRAILER_OUT)
    print(f"\nTRAILER: {TRAILER_OUT}")

if __name__=="__main__": main()

