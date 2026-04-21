lst = ['CampusX is a channel for data-science', 'aspirants.']

result = []

for sentence in lst:
    result.extend(sentence.split())

print(result)