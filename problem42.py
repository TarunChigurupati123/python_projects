lst = [1, 2, 3, 4, 5, 6]

result = list(map(lambda x: x[1] ** x[0], enumerate(lst)))

print(result)