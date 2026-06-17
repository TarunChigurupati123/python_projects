while True:
    user_input = input("Enter a number (or type quit): ")

    if user_input == "quit":
        print("Goodbye!")
        break

    number = int(user_input)

    if number % 2 == 0:
        print("Even")
    else:
        print("Odd")