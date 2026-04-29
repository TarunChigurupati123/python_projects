employees = [
    {"first": "John", "last": "Doe", "age": 30, "grade": "Skilled"},
    {"first": "Jane", "last": "Smith", "age": 28, "grade": "Highly skilled"},
    {"first": "Mike", "last": "Ross", "age": 35, "grade": "Semi-skilled"},
    {"first": "Emily", "last": "Clark", "age": 26, "grade": "Highly skilled"},
    {"first": "David", "last": "Lee", "age": 40, "grade": "Skilled"}
]

# Filter + Map
result = list(
    map(lambda emp: emp["first"] + " " + emp["last"],
        filter(lambda emp: emp["grade"] == "Highly skilled", employees))
)

print(result)