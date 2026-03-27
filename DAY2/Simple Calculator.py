def addd(num1, num2):
    return num1+num2

def sub(num1, num2):
    return num1-num2

def mul(num1, num2):
    return num1*num2

def div(num1, num2):
    return num1/num2
 
while True:
    print("Choose a number to calculate the numbers")
    print("1. Addition")
    print("2. Subtraction")
    print("3. Multiplication")
    print("4. Division")
    print("5. Exit")

    user_choice = input("Enter your choice: ")   

    if user_choice == "1":
        num1 = int(input("Enter first number: "))
        num2 = int(input("Enter second number: "))
        print(addd(num1, num2))
    elif user_choice == "2":
        num1 = int(input("Enter first number: "))
        num2 = int(input("Enter second number: "))
        print(sub(num1, num2))
    elif user_choice == "3":
        num1 = int(input("Enter first number: "))
        num2 = int(input("Enter second number: "))
        print(mul(num1,num2))
    elif user_choice == "4":
        num1 = int(input("Enter first number: "))
        num2 = int(input("Enter second number: "))
        print(div(num1,num2))
    elif user_choice == "5":
        break
    else:
        print("Invalid number, try again..")