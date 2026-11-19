"""Generate the research Ngoc Huyen voice in its isolated ONNX environment."""
import os
import sys
import json
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'local_tts/ViFastTts/src'))
from vifasttts.runtime.onnx_engine import OnnxAcousticModel, OnnxVocoder
from vifasttts.runtime.tts_engine import OnnxTtsEngine, TtsSettings
from vifasttts.frontend.pipeline import parse_text
from local_pronunciation import prepare, restore_units

if __name__ == '__main__':
    acoustic = OnnxAcousticModel(root / 'local_tts/models/acoustic.onnx', provider='cpu')
    vocoder = OnnxVocoder(root / 'local_tts/models/vocoder.onnx', provider='cpu')
    engine = OnnxTtsEngine(acoustic, vocoder)
    spoken, spans, warnings = prepare(sys.argv[1], lambda text: parse_text(text, resolve_oov=False))
    result = engine.synthesize(spoken, TtsSettings(speed=float(sys.argv[3])))
    result.units = restore_units(result.units, spans)
    Path(sys.argv[2]).write_bytes(result.wav)
    Path(sys.argv[2] + '.json').write_text(json.dumps(result.units, ensure_ascii=False), encoding='utf-8')
    Path(sys.argv[2] + '.warnings.json').write_text(json.dumps(warnings, ensure_ascii=False), encoding='utf-8')
