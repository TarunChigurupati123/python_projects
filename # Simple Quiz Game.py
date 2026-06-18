# Simple Quiz Game

score = 0

print("Welcome to the Quiz Game!")
print("--------------------------")

answer = input("1. What is the capital of India? ")

if answer.lower() == "new delhi":
    print("Correct!")
    score += 1
else:
    print("Wrong! The answer is New Delhi.")

answer = input("2. What does CPU stand for? ")

if answer.lower() == "central processing unit":
    print("Correct!")
    score += 1
else:
    print("Wrong! The answer is Central Processing Unit.")

answer = input("3. Which programming language are you learning? ")

if answer.lower() == "python":
    print("Correct!")
    score += 1
else:
    print("Wrong! The answer is Python.")

print("--------------------------")
print("Quiz Finished!")
print("Your score is", score, "out of 3")