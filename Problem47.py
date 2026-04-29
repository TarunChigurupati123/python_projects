class BankAccount:
    def __init__(self, accountNumber, name, balance):
        self.accountNumber = accountNumber
        self.name = name
        self.balance = balance

    def Deposit(self, amount):
        if amount > 0:
            self.balance += amount
        else:
            print("Invalid deposit amount")

    def Withdrawal(self, amount):
        if amount > 0 and amount <= self.balance:
            self.balance -= amount
        else:
            print("Insufficient balance or invalid amount")

    def bankFees(self):
        fee = self.balance * 0.05
        self.balance -= fee

    def display(self):
        print(f"Account Number: {self.accountNumber}")
        print(f"Account Name: {self.name}")
        print(f"Account Balance: {int(self.balance)}")


# Example usage
newAccount = BankAccount(2178514584, "Mandy", 2800)
newAccount.Withdrawal(700)
newAccount.Deposit(1000)
newAccount.display()