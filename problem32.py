s = "green-red-yellow-black-white"

# Split → sort → join
result = "-".join(sorted(s.split("-")))

print(result)