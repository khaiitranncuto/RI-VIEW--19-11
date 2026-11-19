"""Shared voice controls for preview and rendered audio."""
import math
import os
import subprocess

FIELDS = ('pitch', 'warmth', 'clarity', 'energy', 'volume')

def normalize_settings(values):
    values = values or {}
    result = {}
    for key in FIELDS:
        value = float(values.get(key, 50))
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('Thông số giọng phải nằm trong khoảng 0–100.')
        result[key] = value
    return result

def apply_voice_settings(path, values, ffmpeg):
    settings = normalize_settings(values)
    if all(v == 50 for v in settings.values()):
        return
    pitch = 2 ** ((settings['pitch'] - 50) * .08 / 12)
    filters = []
    if pitch != 1:
        filters += [f'asetrate=24000*{pitch}', 'aresample=24000', f'atempo={1/pitch}']
    if settings['warmth'] != 50:
        filters.append(f"bass=g={(settings['warmth']-50)*.12}:f=180")
    if settings['clarity'] != 50:
        filters.append(f"treble=g={(settings['clarity']-50)*.12}:f=3000")
    energy = (settings['energy']-50)/50
    if energy > 0:
        filters.append(f'acompressor=threshold=0.15:ratio={1+energy*3}:attack=8:release=100:makeup={1+energy*.5}')
    elif energy < 0:
        filters.append(f'acompressor=threshold=0.4:ratio={1-energy}:attack=30:release=250')
    filters += [f"volume={1+(settings['volume']-50)/100}", 'alimiter=limit=0.95:level=false']
    base, ext = os.path.splitext(path)
    target = base + '_adjusted' + ext
    subprocess.run([ffmpeg, '-y', '-i', path, '-af', ','.join(filters),
                    '-ar', '24000', target], check=True, capture_output=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    os.replace(target, path)
