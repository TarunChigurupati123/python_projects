lst = [['c', 'a', 'm', 'p', 'u', 'x'],
       ['i','s'],
       ['b', 'e', 's', 't'],
       ['c', 'h', 'a', 'n', 'e', 'l']]

# Step 1: join letters to form words
words = [''.join(chars) for chars in lst]

# Step 2: join words into a sentence
sentence = ' '.join(words)

# Capitalize first letter
sentence = sentence.capitalize()

print(sentence)