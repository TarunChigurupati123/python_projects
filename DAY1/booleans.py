age = 26

can_vote = age <= 25
print(can_vote)

has_license = True
can_vote = age >= 21 and has_license
print(can_vote)

drunk = False

can_vote = age >= 25 and has_license and not drunk
print(can_vote)

