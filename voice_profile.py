"""Prosody supported by Edge TTS; no Azure-only speaking styles or custom SSML."""
VOICE_REVISION = 'native-2'


def voice_prosody(emotion, pitch_hz=0, rate_percent=0, character='soft', kawaii=False):
    emotion = str(emotion).lower()
    emotion = {'happy': 'felice', 'sad': 'triste', 'angry': 'allerta',
               'arrabbiata': 'allerta', 'shock': 'sorpresa', 'love': 'amore'}.get(emotion, emotion)
    if character == 'soft':
        changes = {'felice': (0, 1), 'triste': (0, -2), 'allerta': (0, 0),
                   'sorpresa': (0, 1), 'amore': (0, -1)}
        volume = '+0%'
    elif character == 'cozy':
        changes = {'felice': (2, 3), 'triste': (-2, -4), 'allerta': (0, 1),
                   'sorpresa': (3, 2), 'amore': (1, -2)}
        volume = '-3%'
    else:
        changes = {'felice': (5, 5), 'triste': (-5, -8), 'allerta': (0, 10),
                   'sorpresa': (10, 8), 'amore': (5, -5)}
        volume = '+0%'
    pitch_delta, rate_delta = changes.get(emotion, (0, 0))
    pitch = max(-35, min(20, int(pitch_hz) + pitch_delta + (6 if kawaii else 0)))
    rate = max(-20, min(20, int(rate_percent) + rate_delta))
    return {'pitch': f'{pitch:+d}Hz', 'rate': f'{rate:+d}%', 'volume': volume}
