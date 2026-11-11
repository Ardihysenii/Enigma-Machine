"""Exhaustive Caesar search. Language ranking is a heuristic, not proof of a key."""
import math
import re
from collections import Counter

FREQUENCIES = (.08167,.01492,.02782,.04253,.12702,.02228,.02015,.06094,.06966,.00153,.00772,.04025,.02406,.06749,.07507,.01929,.00095,.05987,.06327,.09056,.02758,.00978,.02360,.00150,.01974,.00074)
COMMON_WORDS = set('''a i the of and to in is you that it he was for on are as with his they at be this have from or one had by word but not what all were we when your can said there use an each which she do how their if will up other about out many then them these so some her would make like him into time has look two more write go see number no way could people my than first water been call who oil its now find long down day did get come made may part hello world attack dawn meet secret message key cipher caesar shift text example test quick brown fox jumps over lazy dog please student teacher course grades school college data information security encrypted encrypt decrypt read send meeting tomorrow morning tonight afternoon good night welcome every hidden story learning letter letters alphabet try combination unknown only know needs need help thank thanks dear friend friends me our us answer result try again success project computer science programming python contains punctuation spaces preserve learning english language change changeable words sample every message has a story at noon dinner bring book books library gate east west north south five three seven nine ten zero open close door password safe demonstration demonstration testing simple learning recover recovered original correctly without knowing fixed different foxes dogs university today see meet me bring your notes at the main entrance never share real private details learning cryptography should be clear easy classroom examination results important appointment moved monday tuesday wednesday thursday friday saturday sunday enough longer sentences automatic analysis reliable useful uncertain best possible candidate confidence all shifts'''.upper().split())
BIGRAMS = set('TH HE IN ER AN RE ON AT EN ND TI ES OR TE OF ED IS IT AL AR ST TO NT NG SE HA AS OU IO LE VE CO ME DE HI RI RO IC NE EA RA CE LI CH LL BE MA SI OM UR'.split())
TRIGRAMS = set('THE AND ING HER ERE ENT THA NTH WAS ETH FOR DTH HAT SHE ION TIO VER EST ERS ATI HIS ALL ITH HES OTH RES ONT REA EAR ONE OUR OUT YOU HEL ELL LLO WOR ORL RLD ATT ACK DAW OWN QUI UIC ICK BRO ROW OWN FOX JUM UMP MPS OVE VER LAZ AZY DOG SEC ECR CRE RET MES ESS SSA SAG AGE SCH CHO HOO OOL STU TUD UDE DEN TEA EAC ACH CHE GRA RAD ADE COU OUR URS RSE'.split())
QUADGRAMS = set('TION NTHE THER THAT OFTH FTHE THES WITH INTH ATIO OTHE TTAC TACK ATTA DAWN HELL ELLO WORL ORLD QUIC UICK BROW ROWN JUMP UMPS OVER LAZY SECR ECRE CRET MESS ESSA SSAG SAGE STUD TUDE UDEN DENT TEAC EACH ACHE CHER GRAD RADE COUR OURS URSE'.split())
RARE = set('QJ QZ QX JQ JX JZ ZX ZQ XQ VQ WQ GQ KQ FQ BQ PQ QG QK QP QV QW QY QH QQ JJ VV'.split())


def decrypt_shift(message, key):
    # Match the existing cipher: uppercase ASCII letters only, preserve everything else.
    return ''.join(chr((ord(c.upper()) - 65 - key) % 26 + 65) if c.isascii() and c.isalpha() else c for c in message)


def language_score(plaintext):
    letters = ''.join(re.findall('[A-Z]', plaintext))
    n = len(letters)
    counts = Counter(letters)
    chi = sum((counts.get(chr(65+i), 0)-n*f)**2/(n*f) for i,f in enumerate(FREQUENCIES)) / n
    # Combine independent clues rather than relying on letter frequency alone.
    bigrams = [letters[i:i+2] for i in range(n-1)]
    trigrams = [letters[i:i+3] for i in range(n-2)]
    quadgrams = [letters[i:i+4] for i in range(n-3)]
    bi = sum(g in BIGRAMS for g in bigrams) / max(1, len(bigrams))
    tri = sum(g in TRIGRAMS for g in trigrams) / max(1, len(trigrams))
    quad = sum(g in QUADGRAMS for g in quadgrams) / max(1, len(quadgrams))
    rare = sum(g in RARE for g in bigrams) / max(1, len(bigrams))
    words = re.findall('[A-Z]+', plaintext)
    coverage = sum(len(w) for w in words if w in COMMON_WORDS) / n
    single_penalty = sum(len(w) == 1 and w not in ('A', 'I') for w in words) / max(1, len(words))
    score = -math.log1p(chi) + 3*bi + 4*tri + 5*quad + 6*coverage - 4*rare - single_penalty
    return score, coverage, bi, tri


def find_caesar_key(message, cipher='caesar'):
    if cipher != 'caesar':
        raise ValueError('Find the key supports Caesar only. Vigenere uses a different key search.')
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise ValueError('Paste encrypted text between 1 and 2,000 characters.')
    try:
        message.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Enter valid Unicode text.') from None
    count = sum(c.isascii() and c.isalpha() for c in message)
    if not count:
        raise ValueError('Include at least one A-Z letter to search for a Caesar key.')
    ranked = []
    evidence = {}
    for key in range(26):
        plaintext = decrypt_shift(message, key)
        score, coverage, bi, tri = language_score(plaintext)
        ranked.append({'key': key, 'plaintext': plaintext, 'score': round(score, 6)})
        evidence[key] = (coverage, bi, tri)
    ranked.sort(key=lambda row: (-row['score'], row['key']))
    gap = ranked[0]['score'] - ranked[1]['score']
    coverage, bi, tri = evidence[ranked[0]['key']]
    plausible = coverage >= .45 or (bi >= .5 and tri >= .2)
    # Never call short samples or near ties reliable. Scores are NOT probabilities.
    likely = count >= 20 and gap >= 1.0 and plausible
    confidence = 'likely' if likely else 'uncertain'
    warning = ('This is the strongest English-language candidate, not a verified key. Check the text before using it.' if likely else
               'The key is uncertain. Short text, names, random data, and other languages may rank incorrectly. Compare the alternatives.')
    return {'mode': 'find_key', 'cipher': 'caesar', 'language': 'English', 'testedKeys': 26,
            'letterCount': count, 'confidence': confidence, 'warning': warning,
            'best': ranked[0], 'candidates': ranked,
            'explanation': 'All 26 shifts, including 0, were tried. Ranking combines English letter frequencies, letter groups and common words. Keys are equivalent modulo 26; the exact original number cannot be recovered.'}
