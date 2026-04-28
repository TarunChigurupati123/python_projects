def get_even_numbers(lst):
    result = []
    for num in lst:
        if num % 2 == 0 and num != 0:
            result.append(num)
    return result


# Sample Input
lst = [1,2,3,4,5,6,7,8,9,0]

print(get_even_numbers(lst))