# Convert Japanese text to phonemes which is
# compatible with Julius https://github.com/julius-speech/segmentation-kit
import re
import unicodedata

# NOTE:
# The original MeloTTS Korean text frontend uses HuggingFace `transformers`
# (via AutoTokenizer + a BERT model) for alignment features. In this project
# we want a **fully local, dependency-light** setup, and we don't need BERT
# conditioning for Korean – the acoustic model can run without it.
#
# To avoid pulling in `transformers` (and its Rust `tokenizers` dependency),
# we remove the import here and rely purely on `g2pkk` + simple text
# normalization for phoneme generation. BERT features are disabled in
# `melo.utils.get_text_for_tts_infer()` for `language_str == "KR"`, so this
# module no longer needs to talk to HuggingFace at all.

from . import punctuation
from .symbols import kr_symbols

from num2words import num2words
from melo.text.ko_dictionary import english_dictionary, etc_dictionary
from anyascii import anyascii
from jamo import hangul_to_jamo

# Allowed symbol set for the Korean model: model's KR symbols + punctuation + pad.
_KR_ALLOWED_SYMBOLS = set(kr_symbols) | set(punctuation) | {"_"}

def normalize(text):
    text = text.strip()
    text = re.sub("[⺀-⺙⺛-⻳⼀-⿕々〇〡-〩〸-〺〻㐀-䶵一-鿃豈-鶴侮-頻並-龎]", "", text)
    text = normalize_with_dictionary(text, etc_dictionary)
    text = normalize_english(text)
    text = text.lower()
    return text


def normalize_with_dictionary(text, dic):
    if any(key in text for key in dic.keys()):
        pattern = re.compile("|".join(re.escape(key) for key in dic.keys()))
        return pattern.sub(lambda x: dic[x.group()], text)
    return text


def normalize_english(text):
    def fn(m):
        word = m.group()
        if word in english_dictionary:
            return english_dictionary.get(word)
        return word

    text = re.sub("([A-Za-z]+)", fn, text)
    return text


def korean_text_to_phonemes(text, character: str = "hangeul") -> str:
    """

    The input and output values look the same, but they are different in Unicode.

    example :

        input = '하늘' (Unicode : \ud558\ub298), (하 + 늘)
        output = '하늘' (Unicode :\u1112\u1161\u1102\u1173\u11af), (ᄒ + ᅡ + ᄂ + ᅳ + ᆯ)

    """
    # Original implementation used `g2pkk` (and indirectly python-mecab-ko),
    # which pulls in heavy native dependencies and can be fragile to build.
    # For this project we simplify things:
    # - normalize the text
    # - convert Hangul syllables directly to Jamo with `hangul_to_jamo`
    # This keeps everything purely in Python and avoids mecab/transformers.

    text = normalize(text)

    if character == "english":
        # For "english" mode, just ASCII‑fold and return.
        text = anyascii(text)
        return text

    # Default: Jamo decomposition for Korean
    jamos = list(hangul_to_jamo(text))  # '하늘' --> ['ᄒ', 'ᅡ', 'ᄂ', 'ᅳ', 'ᆯ']

    # Map any Jamo/symbol not present in the KR symbol set to the padding symbol.
    filtered = [ch if ch in _KR_ALLOWED_SYMBOLS else "_" for ch in jamos]
    return "".join(filtered)

def text_normalize(text):
    # res = unicodedata.normalize("NFKC", text)
    # res = japanese_convert_numbers_to_words(res)
    # # res = "".join([i for i in res if is_japanese_character(i)])
    # res = replace_punctuation(res)
    text = normalize(text)
    return text


def distribute_phone(n_phone, n_word):
    phones_per_word = [0] * n_word
    for task in range(n_phone):
        min_tasks = min(phones_per_word)
        min_index = phones_per_word.index(min_tasks)
        phones_per_word[min_index] += 1
    return phones_per_word



def g2p(norm_text):
    # Lightweight G2P for Korean without `transformers`:
    # - we treat each whitespace-separated token as a "word"
    # - use g2pkk for phoneme conversion
    # - keep punctuation tokens as-is
    #
    # This is simpler than the original subword/BERT-based pipeline, but
    # sufficient for inference when the acoustic model is trained on the
    # same symbol set.
    tokenized = norm_text.split()
    phs = []
    ph_groups = []
    for t in tokenized:
        ph_groups.append([t])
    word2ph = []
    for group in ph_groups:
        text = "".join(group)
        if text == '[UNK]':
            phs += ['_']
            word2ph += [1]
            continue
        elif text in punctuation:
            phs += [text]
            word2ph += [1]
            continue
        phonemes = korean_text_to_phonemes(text)
        phone_len = len(phonemes)
        word_len = len(group)

        aaa = distribute_phone(phone_len, word_len)
        assert len(aaa) == word_len
        word2ph += aaa

        phs += phonemes
    phones = ["_"] + phs + ["_"]
    tones = [0 for i in phones]
    word2ph =  [1] + word2ph + [1]
    assert len(word2ph) == len(tokenized) + 2
    return phones, tones, word2ph

def get_bert_feature(text, word2ph, device='cuda'):
    from . import japanese_bert
    return japanese_bert.get_bert_feature(text, word2ph, device=device, model_id=model_id)


if __name__ == "__main__":
    # tokenizer = AutoTokenizer.from_pretrained("./bert/bert-base-japanese-v3")
    from text.symbols import symbols
    text = "전 제 일의 가치와 폰타인 대중들이 한 일의 의미를 잘 압니다. 앞으로도 전 제 일에 자부심을 갖고 살아갈 겁니다"
    import json

    # genshin_data = json.load(open('/data/zwl/workspace/StarRail_Datasets/Index & Scripts/Index/1.3/Korean.json'))
    genshin_data = json.load(open('/data/zwl/workspace/Genshin_Datasets/Index & Script/AI Hobbyist Version/Index/4.1/KR_output.json'))
    from tqdm import tqdm
    new_symbols = []
    for key, item in tqdm(genshin_data.items()):
        texts = item.get('voiceContent', '')
        if isinstance(texts, list):
            texts = ','.join(texts)
        if texts is None:
            continue
        if len(texts) == 0:
            continue

        text = text_normalize(text)
        phones, tones, word2ph = g2p(text)
        bert = get_bert_feature(text, word2ph)
        import  pdb; pdb.set_trace()
        for ph in phones:
            if ph not in symbols and ph not in new_symbols:
                new_symbols.append(ph)
                print('update!, now symbols:')
                print(new_symbols)
                with open('korean_symbol.txt', 'w') as f:
                    f.write(f'{new_symbols}')

        

# if __name__ == '__main__':
#     from pykakasi import kakasi
#     # Initialize kakasi object
#     kakasi = kakasi()

#     # Set options for converting Chinese characters to Katakana
#     kakasi.setMode("J", "H")  # Chinese to Katakana
#     kakasi.setMode("K", "H")  # Hiragana to Katakana

#     # Convert Chinese characters to Katakana
#     conv = kakasi.getConverter()
#     katakana_text = conv.do('ええ、僕はおきなと申します。こちらの小さいわらべは杏子。ご挨拶が遅れてしまいすみません。あなたの名は?')  # Replace with your Chinese text

#     print(katakana_text)  # Output: ニーハオセカイ