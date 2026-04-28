def count_case(s):
    upper = 0
    lower = 0

    for ch in s:
        if ch.isupper():
            upper += 1
        elif ch.islower():
            lower += 1

    print("No. of Upper case characters:", upper)
    print("No. of Lower case characters:", lower)

s = "CampusX is an Online Mentorship Porgram for Engineering Students"
count_case(s)