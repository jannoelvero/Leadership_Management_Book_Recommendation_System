import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS


FIELD_BOUNDARY = "zzfieldboundaryzz"
STOP_WORDS = set(ENGLISH_STOP_WORDS)


def boundary_aware_analyzer(document):
    features = []

    fields = document.split(FIELD_BOUNDARY)

    for field in fields:
        tokens = re.findall(
            r"(?u)\b[^\W_][\w'-]+\b",
            field.lower()
        )

        tokens = [
            token
            for token in tokens
            if token not in STOP_WORDS
        ]

        features.extend(tokens)

        features.extend(
            [
                f"{tokens[i]} {tokens[i + 1]}"
                for i in range(len(tokens) - 1)
            ]
        )

    return features
