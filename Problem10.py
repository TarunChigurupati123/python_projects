lst = ['campusxIs', 'bestFor', 'dataScientist']

result = []

for word in lst:
    new_word = ""
    for ch in word:
        if ch.isupper():
            new_word += " " + ch
        else:
            new_word += ch
    result.append(new_word)

print(result)