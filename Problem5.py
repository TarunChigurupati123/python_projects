list1 = [2, 4, 6, 10, 1]

result = []

for i in list1:
    s = sum(x for x in list1 if x > i)
    result.append(s)

print(result)