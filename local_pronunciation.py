"""Pronunciation-only spelling; display text stays owned by the script."""
import re
import json
import hashlib
import unicodedata
from pathlib import Path

VERSION = 'names-v2'
OVERRIDES_PATH = Path(__file__).with_name('pronunciation_overrides.json')
READINGS = {
    'kukuru': 'cu cu ru', 'nobita': 'nô bi ta',
    'doraemon': 'đô ra ê mon', 'shizuka': 'shi zu ca',
    'suneo': 'su nê ô', 'giga': 'ghi ga', 'zombie': 'dôm bi',
    'pegasus': 'pê ga sút', 'tsuchidama': 'su chi đa ma',
    'tokoyami': 'tô cô ya mi', 'griffin': 'gờ ríp phin',
}


def load_readings(path=None):
    """Cách đọc người dùng ưu tiên hơn bảng mặc định; cấu hình lỗi phải báo rõ."""
    result = dict(READINGS)
    path = Path(path) if path is not None else OVERRIDES_PATH
    if path.exists():
        values = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(values, dict) or any(
                not isinstance(k, str) or not k.strip() or not isinstance(v, str)
                or not v.strip() for k, v in values.items()):
            raise ValueError('Bảng phát âm phải có dạng {"tên gốc": "cách đọc tiếng Việt"}.')
        result.update({unicodedata.normalize('NFC', k).casefold().strip(): v.strip()
                       for k, v in values.items()})
    return result


def cache_version():
    payload = json.dumps(load_readings(), ensure_ascii=False, sort_keys=True)
    return VERSION + ':' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def approximate_reading(token, parse):
    """Ước lượng tên Latin chưa có cách đọc, chỉ dùng các âm tiết máy hiểu."""
    word = ''.join(c for c in unicodedata.normalize('NFKD', token.casefold())
                   if not unicodedata.combining(c))
    if not re.fullmatch('[a-z]+', word):
        raise ValueError(f'Chưa có cách đọc cho {token!r}; bổ sung pronunciation_overrides.json.')
    # Quy tắc gần âm, không đánh vần tên chữ cái. Tên đã nghe duyệt dùng override.
    replacements = {'tion': 'sơn', 'sh': 'si', 'ch': 'chi', 'th': 'thơ',
                    'ph': 'phơ', 'ck': 'cơ', 'ee': 'i', 'oo': 'u',
                    'ou': 'ao', 'ow': 'ao', 'ai': 'ây', 'ay': 'ây',
                    'qu': 'quy', 'ng': 'ngơ'}
    sounds = {'a': 'a', 'b': 'bơ', 'c': 'cơ', 'd': 'đơ', 'e': 'e',
              'f': 'phơ', 'g': 'gơ', 'h': 'hơ', 'i': 'i', 'j': 'giơ',
              'k': 'cơ', 'l': 'lơ', 'm': 'mơ', 'n': 'nơ', 'o': 'ô',
              'p': 'pơ', 'q': 'quy', 'r': 'rơ', 's': 'sơ', 't': 'tơ',
              'u': 'u', 'v': 'vơ', 'w': 'u', 'x': 'ích', 'y': 'i', 'z': 'dơ'}
    pieces = []
    while word:
        # Giữ nguyên âm tiết Việt hợp lệ dài nhất thay vì tách từng chữ.
        candidate = next((word[:n] for n in range(min(6, len(word)), 1, -1)
                          if re.search('[aeiouy]', word[:n])
                          and _readable(parse(word[:n]))), None)
        special = next((key for key in replacements if word.startswith(key)), None)
        if special:
            pieces.append(replacements[special]); word = word[len(special):]
        elif candidate:
            pieces.append(candidate); word = word[len(candidate):]
        else:
            pieces.append(sounds[word[0]]); word = word[1:]
    reading = ' '.join(pieces)
    if not _readable(parse(reading)):
        raise ValueError(f'Không phiên âm được {token!r}; bổ sung pronunciation_overrides.json.')
    return reading


def _readable(items):
    return bool(items) and not any(str(i.status).endswith('FALLBACK_REQUIRED') for i in items)


def prepare(text, parse, readings=None):
    text = unicodedata.normalize('NFC', text)
    readings = load_readings() if readings is None else {
        unicodedata.normalize('NFC', k).casefold(): v for k, v in readings.items()}
    # Ưu tiên cụm tên dài nhất, chỉ khớp trọn từ, không sửa tên trong phụ đề.
    names = '|'.join(re.escape(k) for k in sorted(readings, key=len, reverse=True))
    pattern = (r'(?<!\w)(?:' + names + r')(?!\w)|\w+|[^\w]+' if names
               else r'\w+|[^\w]+')
    spoken, spans, warnings = [], [], []
    count = 0
    for match in re.finditer(pattern, text, re.UNICODE | re.IGNORECASE):
        token = match.group()
        reading = readings.get(token.casefold(), token)
        items = parse(reading)
        bad = [item for item in items if str(item.status).endswith('FALLBACK_REQUIRED')]
        if bad:
            warnings.append(token)
            if token.casefold() in readings:
                raise ValueError(f'Cách đọc của {token!r} chưa hợp lệ: {reading!r}.')
            reading = approximate_reading(token, parse)
            items = parse(reading)
        spoken.append(reading)
        if reading != token and items:
            spans.append((count, count + len(items), token))
        count += len(items)
    return ''.join(spoken), spans, list(dict.fromkeys(warnings))


def restore_units(units, spans):
    starts = {a: (b, text) for a, b, text in spans}
    result, index = [], 0
    while index < len(units):
        if index in starts:
            end, text = starts[index]
            group = units[index:end]
            result.append(dict(group[0], text=text, end_ms=group[-1]['end_ms'],
                               punctuation=group[-1].get('punctuation', ''),
                               phrase_end=group[-1].get('phrase_end', False),
                               sentence_end=group[-1].get('sentence_end', False)))
            index = end
        else:
            result.append(units[index])
            index += 1
    return result
