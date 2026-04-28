def most_frequent_word(s):
    words = s.split()
    freq = {}

    for word in words:
        freq[word] = freq.get(word, 0) + 1

    max_word = max(freq, key=freq.get)
    return max_word, freq[max_word]


# Sample Input
s = "hello how are you i am fine thank you"

word, count = most_frequent_word(s)
print(f"{word} -> {count}")