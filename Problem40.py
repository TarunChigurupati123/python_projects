from collections import Counter

def bag_of_words(sentences):
    words = []

    for sentence in sentences:
        words.extend(sentence.lower().split())  # normalize + tokenize

    return dict(Counter(words))


# Sample Input
texts = [
    "this is a test",
    "this test is simple",
    "simple test case"
]

print(bag_of_words(texts))