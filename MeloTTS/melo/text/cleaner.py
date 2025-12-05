from . import cleaned_text_to_sequence
import copy

# Lazy import language modules to avoid import errors for unused languages
language_module_map = {}

def _get_language_module(language):
    """Lazy load language modules only when needed"""
    if language not in language_module_map:
        if language == "ZH":
            from . import chinese
            language_module_map["ZH"] = chinese
        elif language == "JP":
            from . import japanese
            language_module_map["JP"] = japanese
        elif language == "EN":
            from . import english
            language_module_map["EN"] = english
        elif language == "ZH_MIX_EN":
            from . import chinese_mix
            language_module_map["ZH_MIX_EN"] = chinese_mix
        elif language == "KR":
            from . import korean
            language_module_map["KR"] = korean
        elif language in ["FR"]:
            from . import french
            language_module_map["FR"] = french
        elif language in ["SP", "ES"]:
            from . import spanish
            language_module_map["SP"] = spanish
            language_module_map["ES"] = spanish
    return language_module_map[language]


def clean_text(text, language):
    language_module = _get_language_module(language)
    norm_text = language_module.text_normalize(text)
    phones, tones, word2ph = language_module.g2p(norm_text)
    return norm_text, phones, tones, word2ph


def clean_text_bert(text, language, device=None):
    language_module = _get_language_module(language)
    norm_text = language_module.text_normalize(text)
    phones, tones, word2ph = language_module.g2p(norm_text)
    
    word2ph_bak = copy.deepcopy(word2ph)
    for i in range(len(word2ph)):
        word2ph[i] = word2ph[i] * 2
    word2ph[0] += 1
    bert = language_module.get_bert_feature(norm_text, word2ph, device=device)
    
    return norm_text, phones, tones, word2ph_bak, bert


def text_to_sequence(text, language):
    norm_text, phones, tones, word2ph = clean_text(text, language)
    return cleaned_text_to_sequence(phones, tones, language)


if __name__ == "__main__":
    pass