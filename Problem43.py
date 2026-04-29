def filter_vowels(s):
    vowels = "aeiou"
    result = list(filter(lambda ch: ch.lower() in vowels, s))
    return result


# Example
s = "CampusX Data Science"
print(filter_vowels(s))