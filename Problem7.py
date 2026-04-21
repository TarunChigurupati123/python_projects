lst = ['1ac21','23fg','456','098d','1','kls']

# numeric strings
nums = [x for x in lst if x.isdigit()]

# non-numeric strings
others = [x for x in lst if not x.isdigit()]

# sort numeric values properly (not as strings)
nums.sort(key=int)

result = nums + others

print(result)