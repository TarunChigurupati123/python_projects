candy_list = ['Jelly Belly','Kit Kat', 'Double Bubble', 'Milky Way', 'Three Musketeers']
no_of_items = [10, 20, 34, 74, 32]

for candy, count in zip(candy_list, no_of_items):
    print(f"{candy} - {count}")